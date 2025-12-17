#!/usr/bin/env bash
set -e

### VARIABLES ###
REPO_URL="https://github.com/N3tGarde/proxreport.git"
INSTALL_DIR="/opt/proxreport"
CONFIG_DIR="/etc/proxreport"
SERVICE_NAME="proxreport"
PYTHON_BIN="/usr/bin/python3"

info() { echo -e "\033[1;34m[INFO]\033[0m $1"; }
warn() { echo -e "\033[1;33m[WARN]\033[0m $1"; }
err()  { echo -e "\033[1;31m[ERROR]\033[0m $1"; exit 1; }

### CHECK ROOT ###
[[ $EUID -ne 0 ]] && err "Debe ejecutarse como root"

info "Directorios que se usarán:"
echo "  Instalación: $INSTALL_DIR"
echo "  Configuración: $CONFIG_DIR"
echo

### COMPROBACIÓN DE INSTALACIÓN EXISTENTE ###
if [[ -d "$INSTALL_DIR/.git" ]] \
   && [[ -f "$CONFIG_DIR/config.ini" ]] \
   && [[ -f "$CONFIG_DIR/users.txt" ]] \
   && [[ -f "/etc/systemd/system/$SERVICE_NAME.service" ]] \
   && systemctl is-active --quiet "$SERVICE_NAME"; then

  info "ProxReport ya está instalado y en ejecución."
  echo "Instalación:   $INSTALL_DIR"
  echo "Configuración: $CONFIG_DIR"
  echo "Servicio:      $SERVICE_NAME (activo)"
  echo
  echo "No se realizará ninguna acción."
  echo "Si desea reinstalar, elimine primero la instalación existente."
  exit 0
fi

### DEPENDENCIAS ###
dependencies=(git python3 openssl)
for cmd in "${dependencies[@]}"; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        warn "$cmd no está instalado."
        read -rp "¿Desea instalar $cmd ahora? [Y/n]: " install_dep
        install_dep=${install_dep:-Y}
        if [[ "$install_dep" =~ ^[Yy]$ ]]; then
            info "Instalando $cmd..."
            apt update && apt install -y "$cmd"
        else
            err "$cmd es obligatorio para continuar."
        fi
    fi
done

### Crear Certificado TLS ###
read -rp "¿Generar TLS autofirmado? [Y/n]: " TLS_ASK
TLS_ASK=${TLS_ASK:-Y}

### CLONAR O ACTUALIZAR REPO ###
if [[ -d "$INSTALL_DIR/.git" ]]; then
  info "Repositorio existente, actualizando..."
  git -C "$INSTALL_DIR" pull
else
  info "Clonando repositorio..."
  git clone "$REPO_URL" "$INSTALL_DIR"
fi

### DIRECTORIOS ###
mkdir -p "$CONFIG_DIR/tls"

### CONFIG.INI ###
if [[ ! -f "$CONFIG_DIR/config.ini" ]]; then
  info "Creando config.ini"
  cp "$INSTALL_DIR/config.example.ini" "$CONFIG_DIR/config.ini"
else
  warn "config.ini ya existe, no se sobrescribirá"
fi

### TLS ###
if [[ "$TLS_ASK" =~ ^[Yy]$ ]]; then
  if [[ ! -f "$CONFIG_DIR/tls/cert.pem" ]]; then
    info "Generando certificado TLS autofirmado"
    openssl req -x509 -newkey rsa:2048 -nodes \
      -keyout "$CONFIG_DIR/tls/key.pem" \
      -out "$CONFIG_DIR/tls/cert.pem" \
      -days 365 \
      -subj "/CN=$(hostname)"
  else
    warn "Certificados TLS ya existen"
  fi
  info "Certificado TLS autofirmado creado"
fi

### Crear Cuenta ###
info "Crear usuario para el dashboard"
read -rp "Nombre de usuario: " ADMIN_USER
ADMIN_USER=${ADMIN_USER:-admin}
info "Introduzca la contraseña:"
PYTHONPATH="$INSTALL_DIR" "$PYTHON_BIN" -m proxreport hash-password --username "$ADMIN_USER" > "$CONFIG_DIR/users.txt"
info "Creando usuario..."
chmod 600 "$CONFIG_DIR/users.txt"

### SYSTEMD ###
info "Instalando servicio systemd"
cp "$INSTALL_DIR/systemd/proxreport.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now "$SERVICE_NAME"

### OBTENER PUERTO HTTPS DESDE CONFIG ###
HTTPS_PORT=$(awk -F= '
  /^[[:space:]]*https_port[[:space:]]*=/ {
    gsub(/[[:space:]]*/, "", $2)
    print $2
  }' "$CONFIG_DIR/config.ini")

### OBTENER IP LOCAL ###
SERVER_IP=$(hostname -I | awk '{print $1}')

# Fallback por seguridad
if [[ -z "$SERVER_IP" ]]; then
  SERVER_IP="127.0.0.1"
fi

info "Instalación completada 🎉"
echo "URL: https://${SERVER_IP}:${HTTPS_PORT}"
echo "Config: $CONFIG_DIR/config.ini"
echo "Logs: journalctl -u $SERVICE_NAME -f"
