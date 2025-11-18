ARG BUILD_FROM
FROM $BUILD_FROM

ENV LANG C.UTF-8

# Install Python en dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip \
    py3-serial

# Install paho-mqtt via pip
RUN pip3 install --no-cache-dir paho-mqtt

# Copy bestanden
COPY run.sh /
COPY ihc_mqtt.py /

RUN chmod a+x /run.sh /ihc_mqtt.py

CMD [ "/run.sh" ]
