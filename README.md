# Launch the service

**Build the image**

```bash
sudo docker build -t chat-bot  .
```

**Run the container**

```bash
sudo docker run --rm -p 8000:8000 --network=host --name chat-bot-container chat-bot
```

# Логика работы бота

Для работы доступны три API команды:
* `/api/building/start` - Инициация диалога бота с пользователем по данному зданию.
* `/api/building/chat` - Общение с ботом.
* `/api/health` - Чат бот жив или нет.

## Логика работы каждого инструмента

* `/api/building/start`

Пример использования:

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

Необходимые параметры для передачи:
* `user_id` - id пользователя
* `buiding_id` - id здания (от Google Maps)
* `facade_img` - изображение фасада здания
* `roof_img` - изображение крыши здания со спутника для анализа дефектов крыши.

Алгоритм инициации диалога:

1. Изображения `facade_img` и `roof_img` отправляются в сервис анализа Антона. В случае успешного запроса получаем ответ в виде текста, данный текст является контекстом для QA агента:



```
building_text = "Жилой комплекс представляет собой современное многоэтажное здание ... "
```

2. Регистрация контекста для данного здания. Необходимо для дальнейшего анализа качества получаемого контекста.

```python
chat_manager.add_context(
          building_id=buiding_id, context=building_text)
```

3. Регистрация текущего контекста для данного пользователя: по контексту какого здания сейчас боту нужно давать информацию данному пользователю.

```python
chat_manager.set_current_context_id(
          user_id=user_id, building_id=buiding_id)
```

4. Инициация чата. Происходит в несколько этапов: <br/>
4.1 Инициация нового Gemini чата:
```python
chat = client.chats.create(
          model=self.model,
          config=types.GenerateContentConfig(
                system_instruction=self.system_prompt
                )
      )
```

4.2 Добавление его в словарь с контекстами по каждому пользователю:
```python
chats[user_id] = chat
```





# Пуск

**ChatBot server**

```bash
uvicorn scripts.app:app --host 0.0.0.0 --port 8000 --reload
```

**Fake abakysis server**
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
