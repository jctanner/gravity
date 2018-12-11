#!/bin/bash

rpm -e --nodeps ansible
yum clean all
yum -y install ansible

rpm -q ansible_utilities_helper || yum -y install ansible_utilities_helper
rpm -q ansible_utilities_logic || yum -y install ansible_utilities_logic
rpm -q ansible_system || yum -y install ansible_system
rpm -q ansible_files || yum -y install ansible_files
rpm -q ansible_commands || yum -y install ansible_commands

ansible-playbook -i 'localhost,' -c local -v site_test.yml
