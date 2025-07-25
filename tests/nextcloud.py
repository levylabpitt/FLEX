from nc_py_api import Nextcloud
from json import dumps


nc = Nextcloud(nextcloud_url="http://nextcloud.levylab.org", nc_auth_user="llab_shared", nc_auth_pass="711elvisshared")
# Specify the directory to search
directory = "/Shared/Data/Stations/THz 1/SA40663G.20250429/"

# List files in the specified directory
files = nc.files.listdir(directory)

# Iterate through the files to find the desired file
for file in files:
    if file.name == "20250519_NoNR_HighRes":
        link = f"https://nextcloud.levylab.org/index.php/f/{file.info.fileid}"
        print(link)