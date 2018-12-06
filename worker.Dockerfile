FROM fedora:29
ENV PYTHONUNBUFFERED 1
RUN mkdir -p /opt/server/src
COPY . /opt/server/src
WORKDIR /opt/server/src/
#RUN rpm -q procps-ng || dnf -y install procps-ng
RUN rpm -q which || dnf -y install which
#RUN which pip3 || dnf -y install python3-pip

RUN rpm -q findutils || dnf -y install findutils
RUN pip3 --help || dnf -y install python3-pip
RUN pip3 install -r requirements.txt

# fpm
RUN rpm -q ruby-devel || dnf -y install ruby-devel
RUN rpm -q gcc || dnf -y install gcc
RUN rpm -q make || dnf -y install make
RUN rpm -q rpm-build || dnf -y install rpm-build
RUN rpm -q libffi-devel || dnf -y install libffi-devel
RUN which fpm || gem install --no-ri --no-rdoc fpm


ENTRYPOINT celery -A tasks worker --loglevel=info
