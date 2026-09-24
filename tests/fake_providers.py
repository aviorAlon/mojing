"""Stand-in generation providers for tests: no network, deterministic output."""
import io

from PIL import Image


def _png(color):
    buf = io.BytesIO()
    Image.new("RGB", (300, 400), color).save(buf, "PNG")
    return buf.getvalue()


class FakeImage:
    name = "fake-image"

    def __init__(self):
        self.calls = []

    def generate(self, prompt, reference=None):
        self.calls.append((prompt, reference is not None))
        return _png("white" if reference is None else "gray")


class FakeVideo:
    """First poll says pending, the second returns a (fake) mp4."""
    name = "fake-video"
    polls = {}

    def submit(self, prompt, first_frame, last_frame, seconds):
        assert first_frame and seconds > 0
        job = f"job-{len(self.polls) + 1}-{'fl' if last_frame else 'f'}"
        self.polls[job] = 0
        return job

    def poll(self, job_id):
        self.polls[job_id] += 1
        if self.polls[job_id] < 2:
            return {"status": "pending"}
        return {"status": "done", "video": b"\x00\x00\x00\x18ftypmp42fake-video"}
