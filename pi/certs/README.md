```
On pi:

$ sudo apt-get install mkcert libnss3-tools
$ mkcert -install
$ mkcert -key-file certs/key.pem -cert-file certs/cert.pem "gripper.local"
```