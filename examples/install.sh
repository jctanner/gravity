#!/bin/bash

# curl https://raw.githubusercontent.com/jctanner/gravity/master/examples/install.sh | bash -

rpm -q epel-release || yum -y install epel-release
if [[ ! -f /etc/yum.repos.d/collections.repo ]]; then
    curl -o /etc/yum.repos.d/collections.repo http://tannerjc.net/ansible/collections.repo
fi

yum clean all
yum -y install ansible
yum -y install ansible-collection-system

FILENAMES="site_1.yml site_2.yml site_3.yml site_4.yml site_5.yml"
for FN in $FILENAMES; do
    if [[ ! -f $FN ]]; then
        curl -o $FN https://raw.githubusercontent.com/jctanner/gravity/master/examples/$FN
    fi
done

# now run each playbook like ...
#   ansible-playbook -i 'localhost,' site_X.yml
