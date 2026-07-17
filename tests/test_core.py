import os
import tempfile
import time
import unittest

from werkzeug.security import check_password_hash

from custom_panel.db import connect, initialize, transaction

class CoreTests(unittest.TestCase):
    def test_schema_and_admin(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "panel.db")
            initialize(path)
            with transaction(path, immediate=True) as conn:
                conn.execute(
                    "INSERT INTO admins(id,username,password_hash,session_version,updated_at) VALUES(1,'admin','hash',1,?)",
                    (int(time.time()),),
                )
            with connect(path) as conn:
                row = conn.execute("SELECT username FROM admins WHERE id=1").fetchone()
                self.assertEqual(row["username"], "admin")

if __name__ == "__main__":
    unittest.main()
