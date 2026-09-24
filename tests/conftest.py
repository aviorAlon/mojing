import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

# API tests run against throwaway copies of the data folders and never load the GPU model
_tmp = tempfile.mkdtemp(prefix="tryon-tests-")
shutil.copytree(os.path.join(ROOT, "catalog"), os.path.join(_tmp, "catalog"))
os.environ.update(TRYON_ENGINE="off", DATA_DIR=os.path.join(_tmp, "data"), CATALOG_DIR=os.path.join(_tmp, "catalog"),
                  LAYA_URL="http://127.0.0.1:9/v1/systemone")
