FROM python:3-alpine

ENV TZ=Asia/Shanghai

WORKDIR /tmp
COPY requirements.txt ./
RUN adduser app -D              && \
    pip install --no-cache-dir -r requirements.txt  && \
    rm -rf /tmp/*

WORKDIR /app
COPY api_server.py ./

EXPOSE 10086
USER app
CMD [ "python3", "./api_server.py" ]
