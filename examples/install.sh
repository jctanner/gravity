#!/bin/bash

rpm -q epel-release || yum -y install epel-release
if [[ ! -f /etc/yum.repos.d/collections.repo ]]; then
    curl -o /etc/yum.repos.d/collections.repo http://tannerjc.net/ansible/collections.repo
fi

yum clean all
yum -y install ansible
yum -y install ansible-collection-system
