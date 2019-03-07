# -*- mode: ruby -*-
# vi: set ft=ruby :

$script = <<SCRIPT
# AUTHENTICATION
echo 'root:vagrant' | chpasswd
echo 'vagrant:vagrant' | chpasswd
egrep "^PasswordAuthentication yes" /etc/ssh/sshd_config
RC=$?
if [[ $RC != 0 ]]; then
    echo "Enabling ssh passwords"
    sed -i.bak 's/PasswordAuthentication\ no/PasswordAuthentication\ yes/' /etc/ssh/sshd_config
    service sshd restart
fi

# BASELINE PACKAGES
PACKAGES="epel-release ansible git vim-enhanced bind-utils policycoreutils-python"
for PKG in $PACKAGES; do
    rpm -q $PKG || yum -y install $PKG
done

# VIMRC
rm -f /etc/vimrc
cp /vagrant/playbooks/files/centos7.vimrc /etc/vimrc

# PSEUDO ANSIBLE-LOCAL PROVISIONER
echo "gravity ansible_host=localhost ansible_connection=local" > /tmp/inv.ini
cd /vagrant/playbooks
ansible-playbook \
    -v \
    -i /tmp/inv.ini \
    site.yml

# HACK IN FIREWALL EXCEPTIONS
systemctl enable firewalld
systemctl restart firewalld
firewall-cmd --zone=public --add-port=80/tcp --permanent
firewall-cmd --reload
setenforce 0

SCRIPT

ENV['VAGRANT_DEFAULT_PROVIDER'] = 'libvirt'

Vagrant.configure("2") do |config|
  config.vm.box = "centos/7"
  #config.vm.box = "fedora/29-cloud-base"
  config.vm.hostname = "gravity.eng.ansible.com"
  config.hostmanager.enabled = true
  config.hostmanager.manage_host = true
  config.hostmanager.manage_guest = true
  config.hostmanager.ignore_private_ip = false
  config.hostmanager.include_offline = true
  config.vm.network "private_network", ip: "192.168.10.190"
  #config.vm.synced_folder ".", "/vagrant", type: "nfs"
  #config.vm.synced_folder ".", "/vagrant", type: "nfs", nfs_udp: true
  config.vm.synced_folder ".", "/vagrant", type: "nfs", nfs_udp: false
  config.vm.provision "shell", inline: $script

  config.vm.provider :libvirt do |libvirt|
    libvirt.cpus = 2
    libvirt.memory = 2048
  end

end
