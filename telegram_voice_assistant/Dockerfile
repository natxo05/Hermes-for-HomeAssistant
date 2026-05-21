ARG BUILD_FROM
FROM $BUILD_FROM

ENV LANG=C.UTF-8 \
    S6_SERVICES_GRACETIME=30000 \
    PIP_ROOT_USER_ACTION=ignore

RUN apk add --no-cache ffmpeg py3-pip python3

COPY requirements.txt /
RUN pip install --no-cache-dir -r /requirements.txt

COPY run.sh /
COPY app /app
RUN chmod a+x /run.sh

WORKDIR /app
CMD ["/run.sh"]
