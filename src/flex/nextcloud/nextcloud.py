from nc_py_api import Nextcloud
from json import dumps
import os

url = 'https://nextcloud.levylab.org'
user = 'llab_shared'
password = os.getenv('NEXTCLOUD_PASSWORD')

class NextcloudHandler:
    def __init__(self, url=url, user=user, password=password):
        self.nc = Nextcloud(nextcloud_url=url, nc_auth_user=user, nc_auth_pass=password)

    def get_file_link(self, directory, filename):
        files = self.nc.files.listdir(directory)
        for file in files:
            if file.name == filename:
                return f"{url}/index.php/f/{file.info.fileid}"
        return None
    
if __name__ == '__main__':
    # nc = NextcloudHandler()
    # print(nc.get_file_link(directory="/Shared/Data/Stations/THz 1/SA40663G.20250429/", filename="20250519_NoNR_HighRes"))
    print(password)