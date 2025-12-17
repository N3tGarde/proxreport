# ProxReport

**ProxReport** es un panel ligero, autoalojado y de una sola página para **Proxmox VE**, orientado a la **monitorización del nodo host** sin depender de la API de Proxmox.

El proyecto está pensado para administradores que quieren una vista clara del estado del host, con un despliegue sencillo, seguro y con dependencias mínimas.

---

## 🎯 Objetivos del proyecto

- Dependencias mínimas (**solo librería estándar de Python**)
- Panel web simple y rápido (one‑page dashboard)
- Monitorización del **host Proxmox**, no del clúster vía API
- Información de salud del sistema y capacidad
- Despliegue **self‑hosted**
- Soporte HTTPS
- Autenticación **HTTP Basic Auth**
- Fácil integración con systemd

---

## 🧱 Qué monitoriza

ProxReport obtiene la información directamente del sistema operativo del host Proxmox:

- CPU (uso y carga)
- Memoria
- Almacenamiento
- Estado general del sistema
- Datos útiles para **capacity planning**

> ⚠️ No utiliza la API de Proxmox. Esto reduce dependencias, complejidad y permisos.

---

## 🚀 Inicio rápido (local / desarrollo)

### 1️⃣ Crear la configuración

Copia el archivo de ejemplo y ajústalo a tu entorno:

```bash
cp config.example.ini config.ini
```

Configura:
- Puertos HTTP / HTTPS
- Rutas de certificados TLS

---

### 2️⃣ Crear certificado TLS autofirmado (ejemplo)

```bash
mkdir -p tls
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout tls/key.pem -out tls/cert.pem \
  -days 365 -subj "/CN=proxreport"
```

---

### 3️⃣ Crear usuarios (Basic Auth)

Genera una entrada de usuario:

```bash
python3 -m proxreport hash-password --username admin
```

El comando pedirá la contraseña y devolverá una línea como:

```text
admin:<salt_hex>:<sha256_hex>
```

Guarda esa línea en el archivo `users.txt`.

---

### 4️⃣ Ejecutar el servicio

```bash
python3 -m proxreport serve --config ./config.ini
```

Accede desde el navegador:

```text
https://<IP_DEL_HOST>:<PUERTO_HTTPS>/
```

> ℹ️ Se recomienda usar **IP** en lugar de hostname si no hay DNS configurado.

---

## 🔍 Smoke tests rápidos

### Comprobar redirección HTTP → HTTPS

```bash
curl -I http://<IP_DEL_HOST>:<PUERTO_HTTP>/
```

### Comprobar autenticación y HTTPS

```bash
curl -k -u usuario:password https://<IP_DEL_HOST>:<PUERTO_HTTPS>/
```

---

## 🧪 Comprobación rápida en Proxmox VE

Para verificar que no hay errores de sintaxis:

```bash
python3 -m py_compile proxreport/*.py
```

---

## 🖥️ Despliegue en Proxmox VE (systemd)

### Estructura recomendada

```text
/opt/proxreport               # Código de la aplicación
/etc/proxreport/config.ini    # Configuración
/etc/proxreport/users.txt     # Usuarios
/etc/proxreport/tls/          # Certificados TLS
  ├── cert.pem
  └── key.pem
```

---

### Pasos de instalación

1️⃣ Copia el repositorio a:

```bash
/opt/proxreport
```

2️⃣ Crea el directorio de configuración:

```bash
mkdir -p /etc/proxreport/tls
```

3️⃣ Copia `config.ini`, `users.txt` y los certificados TLS

4️⃣ Instala el servicio systemd:

```bash
cp systemd/proxreport.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now proxreport
```

---

### Puertos 80 / 443

Si deseas escuchar directamente en los puertos **80/443**, revisa y habilita las líneas de capacidades comentadas en el archivo:

```text
systemd/proxreport.service
```

---

## 🔐 Almacenamiento de contraseñas

Los usuarios se almacenan en el formato:

```text
username:salt_hex:sha256_hex
```

Donde:

```text
sha256_hex = SHA256(salt_bytes + password_utf8)
```

Esto permite:
- No almacenar contraseñas en texto plano
- Mantener una implementación simple
- Evitar dependencias externas (solo Python stdlib)

---

## 📄 Licencia

Este proyecto se distribuye bajo licencia **MIT**.

Consulta el archivo `LICENSE` para más información.

---

## 📌 Proyecto

**Proyecto de Proxmox – ProxReport**  
Panel ligero y seguro para la supervisión del host Proxmox VE.
