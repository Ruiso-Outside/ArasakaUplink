# ARASAKA UPLINK

Arquivos e textos entre o **PC e o celular** pela rede de casa, com o visual da Arasaka. Sem nuvem, sem cabo e
**sem instalar app no celular**: ele lê um QR code e abre uma página no navegador.

## Como usar

1. Abra o **Arasaka Uplink** no PC. Aparece um QR code.
2. No celular, na **mesma rede Wi-Fi**, aponte a câmera para o QR code e abra o link.
3. No PC, **aceite** o aparelho na primeira vez (depois ele fica lembrado).
4. No celular: **Escolher fotos e arquivos** manda para o PC; **Enviar texto** manda um texto ou link.
5. No PC, aba **Enviar**: compartilhe arquivos ou um texto, e o celular baixa ou copia pela página.

Os arquivos recebidos vão para `Downloads/Uplink` (dá para trocar a pasta). Nada é sobrescrito: nomes
repetidos ganham `(1)`, `(2)`... Os arquivos que você compartilha não são copiados: o celular baixa direto do
lugar onde eles estão, enquanto o Uplink estiver aberto.

## Segurança

| Proteção | Como |
|---|---|
| **Só a rede local** | O servidor recusa endereços de fora (aceita só 192.168.x, 10.x, 172.16–31.x, fe80:: e o próprio PC) |
| **Código secreto** | Cada vez que o Uplink abre, sorteia um código novo, que vai no QR code depois do `#` (não aparece em registros) |
| **Aprovação** | Cada aparelho novo precisa ser aceito no PC. Os aceitos ficam lembrados (dá para esquecer na aba Conectar) |
| **Só enquanto aberto** | O servidor existe só com o app aberto, e não registra acessos nem IPs |

**Limite:** a página é **HTTP**. Os navegadores só liberam criptografia em páginas HTTPS, e na rede de casa não há
um certificado válido sem instalar algo no celular. Por isso, use em casa, não em Wi-Fi público.

Se o celular não conectar: os dois precisam estar na mesma rede, e um firewall ligado no PC precisa liberar a porta
(o instalador libera no `ufw` para redes `192.168.x`, se ele estiver ativo).

## Instalar

Pela **Arasaka Central** (Loja → Apps), ou:

```bash
./install.sh
```

Rode **sem sudo**. Para remover: `./uninstall.sh`.

---

Arasaka é marca da CD PROJEKT RED (projeto de fã, sem fins comerciais). A fonte `cedge1` usa a licença
FontStruct Non-Commercial.
