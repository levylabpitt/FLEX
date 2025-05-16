from flex.db import FLEXDB
from typing import List
import logging
import os

def get_usernames_from_db() -> List[str]:
    db = FLEXDB("levylab_test", "llab_admin")
    try:
        result = db.execute_fetch("SELECT levylab_email FROM users", method="all")
        db.close_connection()
        return [row[0].split('@')[0] for row in result]  # Extracting the username before '@'
    except Exception as e:
        logging.error(f"Failed to fetch usernames: {e}")
        db.close_connection()
        return []

def generate_users_py(usernames: List[str], output_file="users.py"):
    script_directory = os.path.dirname(os.path.abspath(__file__))
    output_file = os.path.join(script_directory, output_file)

    with open(output_file, "w") as f:
        f.write("# Auto-generated from database\n")
        f.write("from typing import Literal\n\n")
        if not usernames:
            f.write("UserLiteral = Literal[None]  # No users found\n")
            return
        literal_list = ", ".join([f"'{u}'" for u in usernames])
        f.write(f"User = Literal[{literal_list}]\n")

if __name__ == "__main__":
    users = get_usernames_from_db()
    generate_users_py(users)
    print(f"users.py generated with {len(users)} users.")
