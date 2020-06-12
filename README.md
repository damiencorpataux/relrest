RelRest
=

**A Relational REST Interface.**

[![Build Status](https://travis-ci.org/damiencorpataux/relrest.svg?branch=master)](https://travis-ci.org/damiencorpataux/relrest?branch=master)
[![codecov](https://codecov.io/gh/damiencorpataux/relrest/graph/badge.svg)](https://codecov.io/gh/damiencorpataux/relrest)
...unittests are #todo


Summary
-
Fetch the events summary, time, and their tag color
of all events that happened before the millenium and are related to tags containing bill?
Here we go!
```
GET /resource/+/+/event.time,event.summary,tag.color?/event.time.lt=2000-01-01/tag.id.like=%bill%
```

Easily retrieve relational data
-
Up to an arbitrary depth and number of relationships. 

[![IMAGE ALT TEXT HERE](https://img.youtube.com/vi/ZPpMVd1nL-U/0.jpg)](https://www.youtube.com/watch?v=ZPpMVd1nL-U)
[![IMAGE ALT TEXT HERE](https://img.youtube.com/vi/AdiE3PbqxF4/0.jpg)](https://www.youtube.com/watch?v=AdiE3PbqxF4)


Run the example REST service
-
In this example, RelRest is integrated into Flask for the HTTP layer, including authentication. 
```
git clone git@github.com:damiencorpataux/relrest.git
cd relrest

python3 -m venv venv
. venv/bin/activate

cd example
pip3 install -r requirements.txt
python -c "import data; data.populate()"
flask run

open http://localhost:5000
```
