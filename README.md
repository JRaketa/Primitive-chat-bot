# Launch the service

**Build the image**

```bash
sudo docker build -t chat-bot  .
```

**Run the container**

```bash
sudo docker run --rm -p 8000:8000 --network=host --name chat-bot-container chat-bot
```

# Commands

* `/api/building/start` - Init a dialog with bot about one building.
* `/api/building/chat` - Chat with bot.
* `/api/health` - Either bot alive or not.

## Usage

* `/api/building/start`

Curl example:

```curl
curl -X 'POST' \
  'http://0.0.0.0:8000/api/building/start' \
  -H 'accept: application/json' \
  -H 'Content-Type: multipart/form-data' \
  -F 'user_id=ID1' \
  -F 'buiding_id=BD1' \
  -F 'facade_img=@img1.jpg;type=image/jpeg' \
  -F 'roof_img=@img2.jpg;type=image/jpeg'
```

Parameters:
* `user_id`
* `buiding_id`
* `facade_img` building's facade image (png, jpeg).
* `roof_img` - building's roof image from satellite for roof defect analysis.

* `/api/building/chat`

* `/api/health`

* `/api/building/history`

* `/api/building/users`

* `/api/building/context`


**ChatBot server**

```bash
uvicorn scripts.app:app --host 0.0.0.0 --port 8000 --reload
```

**Fake analysis server**
```bash
uvicorn scripts.analyse:app --host 0.0.0.0 --port 8080 --reload
```

**Available models**
* gemini-2.5-flash-lite - Smallest, fastest
* <u>gemini-2.5-flash</u> - Balanced performance
* gemini-2.5-pro - Most capable
* gemini-3-pro-preview - Latest features

**Gemini SDK docs**

```url
https://deepwiki.com/google-gemini/cookbook/9.1-python-sdk
```

**Chat paragraph**

```url
https://deepwiki.com/google-gemini/cookbook/9.1-python-sdk#:~:text=stateful%20chat%20sessions%3A-,chat%20%3D%20client.chats.create(,),-%23%20Send%20messages
```
