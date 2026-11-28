import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from database.connection import DatabaseManager
db = DatabaseManager.get_db()
users = list(db.users.find({}, {'password_hash': 0}))
print(f"Total Users: {len(users)}")
for u in users:
    emp_id = u.get('employee_id', '--')
    email = u.get('email', '--')
    role = u.get('role', '--')
    name = u.get('full_name', '--')
    print(f"  {emp_id:12} | {email:30} | {role:15} | {name}")
