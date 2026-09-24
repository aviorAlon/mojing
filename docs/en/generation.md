# Generation Models (Optional)

Three parts of the project need "generation" capability. None of them is **configured by default**; you plug in your own models:

| Purpose | Entry point | Configuration needed |
|---|---|---|
| Generate mock garments (flat-lay front + back) | `tools/generate_catalog.py` | Image model |
| Generate mock sample people (front / side / back) | `tools/generate_person.py` | Image model |
| "Generate turnaround video" (生成转身视频) on the website | The button below the try-on result | Video model |

When nothing is configured, these entry points fail with an error that tells you which variables to set. Try-on itself does not depend on them. The demo garments and the two sample people bundled with the repo work out of the box.

## Image model

### Option 1: OpenAI-compatible Images API (built in)

Set in `.env`:

```ini
IMAGE_API_BASE=https://api.openai.com/v1     # any service compatible with the OpenAI Images API
IMAGE_API_KEY=sk-...
IMAGE_MODEL=gpt-image-1
IMAGE_SIZE=1024x1536                         # portrait, suits garments and full-body photos
```

How it is called:

- Without a reference image: `POST {IMAGE_API_BASE}/images/generations`, JSON `{"model", "prompt", "size", "n": 1}`.
- With a reference image: `POST {IMAGE_API_BASE}/images/edits`, multipart with fields `image`, `model`, `prompt`, `size`. Used when generating a garment's back and a person's side and back views, so they show the same garment / same person as the front.
- The response may return either `data[0].b64_json` or `data[0].url`.

### Option 2: your own implementation

Write a class under `plugins/`, then set `IMAGE_PROVIDER=module:ClassName`:

```python
# plugins/my_image.py
class MyImageProvider:
    name = "my-image-model"

    def generate(self, prompt: str, reference: bytes | None = None) -> bytes:
        """Return PNG/JPEG bytes. With a reference, keep its subject (same garment / same person) and render the new view described by the prompt."""
        ...
```

```ini
IMAGE_PROVIDER=my_image:MyImageProvider
```

`IMAGE_PROVIDER` takes precedence over `IMAGE_API_KEY`.

## Video model

Video generation APIs differ widely between vendors, so only the plugin approach is supported. Implement under `plugins/`:

```python
# plugins/my_video.py
import os
import httpx


class MyVideoProvider:
    name = "my-video-model"

    def __init__(self):
        self.key = os.environ["MY_VIDEO_KEY"]          # put your own settings in .env

    def submit(self, prompt: str, first_frame: bytes, last_frame: bytes | None, seconds: int) -> str:
        """Submit a job and return its id.
        first_frame: front try-on result (JPEG); last_frame: back try-on result, or None when there is no back view.
        With first and last frames the prompt describes "turning from front to back"; with only a first frame it describes "turning around in place"."""
        r = httpx.post("https://video.example.com/v1/jobs", headers={"Authorization": f"Bearer {self.key}"},
                       files={"first_frame": first_frame, **({"last_frame": last_frame} if last_frame else {})},
                       data={"prompt": prompt, "duration": seconds})
        r.raise_for_status()
        return r.json()["id"]

    def poll(self, job_id: str) -> dict:
        """Return {"status": "pending"} / {"status": "done", "video": mp4 bytes} / {"status": "failed", "error": "reason"}."""
        job = httpx.get(f"https://video.example.com/v1/jobs/{job_id}", headers={"Authorization": f"Bearer {self.key}"}).json()
        if job["state"] == "succeeded":
            return {"status": "done", "video": httpx.get(job["video_url"]).content}
        if job["state"] == "failed":
            return {"status": "failed", "error": job.get("error")}
        return {"status": "pending"}
```

```ini
VIDEO_PROVIDER=my_video:MyVideoProvider
VIDEO_SECONDS=5
```

The URLs and fields above are only illustrative; replace them with your service's actual API. The website polls `poll` every 5 seconds and saves the video to `data/videos/` once it arrives. After changing the configuration, run `python scripts/run.py restart`.

Nothing under `plugins/` except `README.md` is committed to git, so it is safe to read secrets there.

## Generating mock garments

Garments are defined in `tools/catalog_spec.json`: title, category, price, attributes, size chart, model reference, suitable occasions, and descriptions of the front and back. Add an entry in that format, then:

```bash
.venvs/tryon/bin/python tools/generate_catalog.py                          # generate garments not yet in catalog/
.venvs/tryon/bin/python tools/generate_catalog.py --only my_item --force   # regenerate one item
.venvs/tryon/bin/python tools/generate_catalog.py --spec my.json --out other_catalog/
```

For each garment the front flat-lay is generated first and then used as the reference for the back, so both sides show the same garment. Every field is marked `source="mock"`.

## Generating mock sample people

```bash
.venvs/tryon/bin/python tools/generate_person.py --out samples/persons/sample_new \
    --gender female --height 165 --weight 55 --look "a fictional Chinese woman around 30, medium build, low black ponytail"

# register it on a running site right away: it goes through exactly the same photo checks and credibility checks as a user upload
.venvs/tryon/bin/python tools/generate_person.py --out /tmp/p1 --gender male --height 175 --weight 70 \
    --look "a fictional Chinese man around 35, slim, short hair" --register http://127.0.0.1:7860
```

Following the upload guidance, generated people wear a fitted T-shirt and shorts. The front is generated first, then used as the reference for the side and back. Describe fictional people only; do not use this to generate real people.

To add the result to `samples/persons/` as a bundled sample: register it on the site with `--register`, then copy `data/persons/<id>/` over as described in the [development guide](development.md#adding-bundled-sample-people).
