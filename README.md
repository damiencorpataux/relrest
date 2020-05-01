REST Joint
=
**A REST Interface based on SQL Joins for CRUD operation on Relational Databases,
with role-based access control on resouces.**

Fetch the summary and time (and their tag color)
of all events that happened before the millenium
and are related to tags ids greater than 50? Easy!
```
/resource/+/+/event.time,event.summary,tag.color?/event.time.lt=2000-01-01/tag.id.gt=50
```

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
flask run

open http://localhost:5000
```
