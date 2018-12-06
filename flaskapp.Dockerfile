#FROM python:3
FROM fedora:29
MAINTAINER James Tanner <tanner.jc@gmail.com>

ENV PYTHONUNBUFFERED 1
RUN mkdir -p /opt/server/src
COPY . /opt/server/src
WORKDIR /opt/server/src/
#RUN rpm -q procps-ng || dnf -y install procps-ng
#RUN rpm -q which || dnf -y install which
#RUN which pip3 || dnf -y install python3-pip
RUN rpm -q findutils || dnf -y install findutils
RUN pip3 --help || dnf -y install python3-pip
RUN pip3 install -r requirements.txt
EXPOSE 5000
CMD ["python3", "flaskapp.py"]
