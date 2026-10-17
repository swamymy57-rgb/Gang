
# My Learning Assistant

Gemini API key లేకుండా పనిచేసే ప్రాథమిక వెబ్ శోధన మరియు మెమరీ ప్రాజెక్ట్.

## Project Files

- `main.py` - ప్రధాన Python వెబ్ అప్లికేషన్.
- `requirements.txt` - అప్లికేషన్‌కు అవసరమైన Python ప్యాకేజీలు.
- `render.yaml` - Render హోస్టింగ్ సెట్టింగులు.
- `README.md` - ప్రాజెక్ట్ వివరాలు మరియు ప్రారంభ సూచనలు.
- `old_main.py` - పాత కోడ్ బ్యాకప్ మాత్రమే; ప్రధాన అప్లికేషన్ దీన్ని ఉపయోగించదు.
- `Old_requirements.txt` - పాత ప్యాకేజీల జాబితా బ్యాకప్ మాత్రమే.

## Features

- మొబైల్‌లో ఉపయోగించగల వెబ్ పేజీ.
- Wikipediaలో ప్రశ్నల కోసం శోధన.
- ప్రశ్నలు మరియు సమాధానాలను SQLiteలో భద్రపరచడం.
- గతంలో అడిగిన ప్రశ్నలకు మెమరీ నుంచి సమాధానం ఇవ్వడం.
- `/health` ద్వారా సర్వర్ స్థితి తనిఖీ.
- `/memory/count` ద్వారా నిల్వ చేసిన జ్ఞాపకాల సంఖ్య చూడటం.

## Requirements

Python 3.11 or a compatible Python version.

## Install Dependencies

pip install -r requirements.txt

## Start the Application

uvicorn main:app --host 0.0.0.0 --port 8000

## Render Deployment

Build Command:

pip install -r requirements.txt

Start Command:

uvicorn main:app --host 0.0.0.0 --port $PORT

## Test Endpoints

- `/` - వెబ్ అప్లికేషన్.
- `/health` - సర్వర్ స్థితి.
- `/docs` - API పరీక్షించే పేజీ.
- `/memory/count` - మెమరీలోని రికార్డుల సంఖ్య.

## Important Notes

This is a basic web search and memory application.
It is not a full AI language model.

Wikipedia availability and internet access are required
for new searches.

For persistent memory on Render, configure persistent
storage or an external database and set MEMORY_DB to
a database path on that storage.

Old backup files are not used by the Render start command.
