RelRest
=
**A REST Interface based on SQL Joins for CRUD operation on Relational Databases,
with role-based access control on resouces.**

Fetch the events summary, time, and their tag color
of all events that happened before the millenium and are related to tags containing bill?
Easy!
```
/resource/+/+/event.time,event.summary,tag.color?/event.time.lt=2000-01-01/tag.id.like=%bill%
```

Run the example rest service
-
```
git clone <repository>
cd relrest

python3 -m venv venv
. venv/bin/activate

cd example
pip3 install -r requirements.txt
python -c "import data; data.populate()"
flask run

open http://localhost:5000
```
