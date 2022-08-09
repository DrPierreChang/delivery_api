FROM ubuntu:18.04

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y software-properties-common curl \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get remove -y software-properties-common \
    && apt-get autoremove -y \
    && apt-get update \
    && apt-get install -y python3.6 python3.6-distutils \
    && curl -o /tmp/get-pip.py "https://bootstrap.pypa.io/pip/3.6/get-pip.py" \
    && python3.6 /tmp/get-pip.py \
    && apt-get install -y git ntp libpq-dev libtiff5-dev libjpeg8-dev \
    	zlib1g-dev libfreetype6-dev liblcms2-dev libwebp-dev tcl8.6-dev tk8.6-dev python-tk gettext \
    	libpython3.6-dev \
	&& rm /usr/bin/python && ln -s /usr/bin/python3.6 /usr/bin/python \
	# clear apt lists to save some space
	&& rm -rf /var/lib/apt/lists/*

COPY ./requirements-3.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt && rm /tmp/requirements.txt && rm -r /root/.cache/pip

COPY . /code
WORKDIR /code

RUN python ./manage.py compilemessages

EXPOSE 8000
