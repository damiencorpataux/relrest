REST Joint
=
**A REST Interface based on SQL Joins for CRUD operation on Relational Databases.**

Run the example rest service
-
```
git clone <repository>
cd restjoint

python3 -m venv venv
. venv/bin/activate
pip3 install -r requirements.txt

cd example
python -c "import data; data.populate()"
python -m app

open "localhost:5000"
```