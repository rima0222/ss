import base64,ipaddress,json,os,pwd,re,subprocess,tempfile
from pathlib import Path
from flask import current_app
USER_RE=re.compile(r'^[a-z_][a-z0-9_-]{0,30}$')

def run(args,input_text=None,check=True):
    return subprocess.run(args,input=input_text,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20,check=check)

def valid_user(u):
    if not USER_RE.fullmatch(u): raise ValueError('نام کاربری لینوکس نامعتبر است.')

class SSH:
    name='ssh'
    def create(self,u):
        valid_user(u['username'])
        username=u['username']
        exists=subprocess.run(['getent','passwd',username],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
        if exists:
            # Adopt a leftover account from a previous interrupted create operation.
            result=run(['usermod','-s','/usr/sbin/nologin',username],check=False)
            if result.returncode!=0:
                raise RuntimeError(result.stderr.strip() or 'Failed to update existing Linux account')
        else:
            # -N prevents failure when a same-name group already exists from an earlier attempt.
            result=run(['useradd','-M','-N','-s','/usr/sbin/nologin',username],check=False)
            if result.returncode!=0:
                # A concurrent/partial operation may have created it meanwhile. Adopt it when present.
                if subprocess.run(['getent','passwd',username],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode!=0:
                    raise RuntimeError(result.stderr.strip() or f'useradd failed with status {result.returncode}')
        result=run(['chpasswd'], f"{username}:{u['password']}\n",check=False)
        if result.returncode!=0:
            raise RuntimeError(result.stderr.strip() or 'Failed to set Linux account password')
        run(['usermod','-U',u['username']])
    update=create
    def pause(self,u): run(['usermod','-L',u['username']]); run(['pkill','-KILL','-u',u['username']],check=False)
    def resume(self,u): run(['usermod','-U',u['username']])
    def delete(self,u): run(['pkill','-KILL','-u',u['username']],check=False); run(['userdel','-r',u['username']],check=False)
    def client(self,u):
        content = f"Host: {current_app.config['SERVER_HOST']}\nPort: 22\nUsername: {u['username']}\nPassword: {u['password']}\n"
        return {'type':'text','filename':f"{u['username']}-ssh.txt",'content':content}
class WireGuard:
    name='wireguard'
    conf=Path('/etc/wireguard/custom-panel-peers.json')
    def _all(self):
        try: return json.loads(self.conf.read_text())
        except Exception: return {}
    def _save(self,d): self.conf.parent.mkdir(parents=True,exist_ok=True); self.conf.write_text(json.dumps(d,indent=2)); os.chmod(self.conf,0o600)
    def create(self,u):
        d=self._all(); name=u['username']
        if name in d: return
        priv=run(['wg','genkey']).stdout.strip(); pub=run(['wg','pubkey'],priv+'\n').stdout.strip()
        used={x['address'] for x in d.values()}; address=None
        for ip in ipaddress.ip_network('10.66.0.0/24').hosts():
            if str(ip)=='10.66.0.1': continue
            if str(ip) not in used: address=str(ip); break
        if not address: raise RuntimeError('WireGuard pool is full')
        d[name]={'private_key':priv,'public_key':pub,'address':address}; self._save(d)
        run(['wg','set',current_app.config['WG_INTERFACE'],'peer',pub,'allowed-ips',address+'/32'])
    def pause(self,u):
        x=self._all().get(u['username']);
        if x: run(['wg','set',current_app.config['WG_INTERFACE'],'peer',x['public_key'],'remove'],check=False)
    def resume(self,u):
        x=self._all().get(u['username']);
        if x: run(['wg','set',current_app.config['WG_INTERFACE'],'peer',x['public_key'],'allowed-ips',x['address']+'/32'])
    def delete(self,u):
        d=self._all(); x=d.pop(u['username'],None)
        if x: run(['wg','set',current_app.config['WG_INTERFACE'],'peer',x['public_key'],'remove'],check=False); self._save(d)
    def update(self,u): return None
    def client(self,u):
        x=self._all().get(u['username']);
        if not x: raise RuntimeError('WireGuard profile not found')
        server_pub=Path('/etc/wireguard/server.pub').read_text().strip()
        c=f"""[Interface]
PrivateKey = {x['private_key']}
Address = {x['address']}/32
DNS = 1.1.1.1

[Peer]
PublicKey = {server_pub}
Endpoint = {current_app.config['SERVER_HOST']}:{current_app.config['WG_PORT']}
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
"""
        return {'type':'wireguard','filename':f"{u['username']}.conf",'content':c}

class OpenVPN:
    name='openvpn'; base=Path('/etc/openvpn/server')
    def create(self,u):
        name=u['username']; valid_user(name); er=self.base/'easy-rsa'
        if not (er/'pki'/'issued'/f'{name}.crt').exists():
            run([str(er/'easyrsa'),'--batch','build-client-full',name,'nopass'])
    def pause(self,u):
        # Revocation is destructive; pause through CCD deny marker and disconnect.
        p=self.base/'clients'/f"{u['username']}.disabled"; p.parent.mkdir(parents=True,exist_ok=True); p.write_text('disabled')
        run(['pkill','-HUP','openvpn'],check=False)
    def resume(self,u): (self.base/'clients'/f"{u['username']}.disabled").unlink(missing_ok=True)
    def delete(self,u):
        er=self.base/'easy-rsa'; run([str(er/'easyrsa'),'--batch','revoke',u['username']],check=False); run([str(er/'easyrsa'),'gen-crl'],check=False)
    def update(self,u): return None
    def client(self,u):
        n=u['username']; er=self.base/'easy-rsa'; host=current_app.config['SERVER_HOST']; port=current_app.config['OVPN_PORT']
        def read(p): return Path(p).read_text().strip()
        c=f"""client
dev tun
proto udp
remote {host} {port}
resolv-retry infinite
nobind
persist-key
persist-tun
remote-cert-tls server
auth SHA256
cipher AES-256-GCM
verb 3
<ca>
{read(self.base/'ca.crt')}
</ca>
<cert>
{read(er/'pki'/'issued'/f'{n}.crt')}
</cert>
<key>
{read(er/'pki'/'private'/f'{n}.key')}
</key>
<tls-crypt>
{read(self.base/'tls-crypt.key')}
</tls-crypt>
"""
        return {'type':'text','filename':f'{n}.ovpn','content':c}

class IKEv2:
    name='ikev2'; path=Path('/etc/swanctl/conf.d/custom-panel-users.conf')
    def _all(self):
        p=Path('/etc/custom-panel/data/ike-users.json')
        try:return json.loads(p.read_text())
        except Exception:return {}
    def _save(self,d):
        p=Path('/etc/custom-panel/data/ike-users.json'); p.write_text(json.dumps(d,indent=2)); os.chmod(p,0o600)
        lines=['secrets {']
        for n,pw in d.items(): lines += [f'  eap-{n} {{',f'    id = {n}',f'    secret = "{pw.replace(chr(34), "")}"','  }']
        lines += ['}']; self.path.write_text('\n'.join(lines)+'\n'); run(['swanctl','--load-creds'],check=False)
    def create(self,u): d=self._all(); d[u['username']]=u['password']; self._save(d)
    update=create
    def pause(self,u): d=self._all(); d.pop(u['username'],None); self._save(d); run(['swanctl','--terminate','--ike',u['username']],check=False)
    def resume(self,u): self.create(u)
    def delete(self,u): self.pause(u)
    def client(self,u):
        ca=Path(current_app.config['IKE_CA']).read_text()
        c=f"Server: {current_app.config['SERVER_HOST']}\nVPN type: IKEv2\nUsername: {u['username']}\nPassword: {u['password']}\nInstall the CA certificate if your OS does not already trust it.\n"
        return {'type':'bundle','filename':f"{u['username']}-ikev2.txt",'content':c,'ca':ca}

REGISTRY={'ssh':SSH(),'wireguard':WireGuard(),'openvpn':OpenVPN(),'ikev2':IKEv2()}
