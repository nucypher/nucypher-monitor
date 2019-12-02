import os
import tempfile

import pytest
from selenium.webdriver.chrome.options import Options


@pytest.fixture(scope="function")
def tempfile_path():
    fd, path = tempfile.mkstemp()
    yield path
    os.close(fd)
    if os.path.exists(path):
        os.remove(path)


# dash[testing] hoo
def pytest_setup_options():
    options = Options()
    options.add_argument('--window-size=1920,1080')  # required to make elements visible to selenium
    options.add_argument('--start-maximized')
    options.add_argument('--headless')
