#!/bin/bash

rpm -e --nodeps ansible
yum clean all
yum -y install ansible

COLS="ansible_utilities_helper ansible_utilities_logic ansible_system ansible_files ansible_commands"
for COL in $COLS; do
	rpm -q $COL && rpm -e --nodeps $COL
	yum -y install $COL
done

ansible-playbook -i 'localhost,' -c local -v site_test.yml
