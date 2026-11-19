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

## Usar os apps do PC pelo celular (controle remoto)

Na página do celular, aba **Apps**: aparecem todos os apps Arasaka e os módulos da Arasaka Central instalados no PC.
Toque num deles: ele abre no PC (ou vem para a frente, se já estiver aberto) e a janela aparece ao vivo no celular.

| No celular | No PC |
|---|---|
| Tocar | Clique |
| Segurar | Botão direito |
| Arrastar com um dedo | Arrastar (selecionar, mover) |
| Dois dedos para cima/baixo | Rolar |
| **TECLADO** | Digita no app (acentos vão pela área de transferência) |
| ENTER, ⌫, ESC, TAB, setas, CTRL+C/V/Z/A/S, DEL, F5 | As mesmas teclas |
| **JANELAS** / **TELA INTEIRA** | Troca a janela vista ou mostra a tela toda |
| **QUALIDADE** | Baixa, normal ou alta (rede mais lenta: baixa) |

Gire o celular para ver maior. A imagem vem a até 10 quadros por segundo, e só os quadros que mudaram são enviados.

**Permissão própria:** a primeira vez que um aparelho pede para ver e controlar, o PC pergunta (**Permitir**,
**Só desta vez** ou **Recusar**). Enquanto alguém estiver vendo, aparece uma **barra vermelha no topo da tela do PC**
com o nome do aparelho e o botão **ENCERRAR**. Na aba Conectar dá para desligar o controle remoto de vez.

Funciona na sessão **Xorg (X11)**. No Wayland, o sistema não deixa um app capturar a tela e mexer no mouse sem um portal
com permissão; se a sua sessão for Wayland, escolha "Zorin OS on Xorg" (ou "Ubuntu on Xorg") na tela de login.

## Usar o celular pelo PC (aba Celular, Android)

Para o dia em que a tela do celular quebrar: o PC espelha e controla o celular, mexe nos arquivos e **resgata tudo**
(fotos, vídeos, documentos, downloads, gravações e a mídia do WhatsApp e do Telegram), sem precisar tocar no celular.
Usa o **ADB** (a depuração do próprio Android) e o **scrcpy** (espelhamento de tela), que o instalador coloca.

**Consentimento no celular, uma vez (com a tela funcionando):**
1. Configurações > Sobre o telefone > toque 7 vezes em **Número da versão** (liga as Opções do desenvolvedor).
2. Opções do desenvolvedor > ligue **Depuração USB** e **Depuração sem fio**.
3. **Pelo Wi-Fi:** Depuração sem fio > **Parear dispositivo com QR code** > leia o QR que aparece no Uplink.
4. **Pelo cabo (o mais garantido):** ligue no USB e marque **"Sempre permitir neste computador"**.

Depois disso o celular não pergunta mais nada: o Uplink reconecta sozinho quando ele aparece na rede (ou no cabo).

**No PC, sempre a sua senha do Linux:** a aba Celular começa trancada. **Destravar com a senha** abre a janela de senha do
próprio sistema (polkit; a senha nunca passa pelo Uplink) e vale 15 minutos sem uso, ou até **Trancar agora**.

| Na aba Celular | O que faz |
|---|---|
| **Espelhar e controlar** | Abre a tela do celular numa janela: mouse e teclado do PC mexem nele (opção de manter a tela do celular apagada) |
| Acordar, Início, Voltar, Recentes, Deslizar, Apagar tela | As teclas e gestos do celular, mesmo sem tela |
| **Digitar / PIN** | Digita no celular (com um PIN, aperta Enter: desbloqueia com a tela quebrada) |
| **Arquivos** | Navega no armazenamento do celular, copia para o PC e manda arquivos do PC para lá |
| **Resgatar tudo** | Copia as pastas importantes para uma pasta nova no PC |

**Para não ficar sem acesso:**
- A **autorização pelo cabo não expira**: é ela que garante o acesso com a tela quebrada. Faça uma vez, com o cabo.
- A **Depuração sem fio** desliga quando o celular sai do Wi-Fi e, em alguns aparelhos, quando reinicia. Pelo Wi-Fi, o
  acesso dura enquanto ela estiver ligada.
- Com a tela travada por senha/PIN, os arquivos só aparecem depois de desbloquear (use **Digitar / PIN**).

**Transparência:** o Android mostra uma notificação fixa enquanto a depuração estiver conectada, e tudo se desfaz no celular
em Opções do desenvolvedor > **Revogar autorizações de depuração USB**. A senha protege o caminho pelo Uplink; o `adb`
continua disponível no terminal da sua conta, como em qualquer PC com ADB.

## Segurança

| Proteção | Como |
|---|---|
| **Só a rede local** | O servidor recusa endereços de fora (aceita só 192.168.x, 10.x, 172.16–31.x, fe80:: e o próprio PC) |
| **Código secreto** | Cada vez que o Uplink abre, sorteia um código novo, que vai no QR code depois do `#` (não aparece em registros) |
| **Aprovação** | Cada aparelho novo precisa ser aceito no PC. Os aceitos ficam lembrados (dá para esquecer na aba Conectar) |
| **Só enquanto aberto** | O servidor existe só com o app aberto, e não registra acessos nem IPs |

**Limite:** a página é **HTTP**. Isso vale também para o controle remoto: a imagem da tela e o que você digita passam sem criptografia pela rede de casa. Os navegadores só liberam criptografia em páginas HTTPS, e na rede de casa não há
um certificado válido sem instalar algo no celular. Por isso, use em casa, não em Wi-Fi público.

## Se o celular não abrir a página

1. **Firewall do PC (o mais comum):** com o `ufw` ligado, a aba Conectar mostra um aviso no topo. Clique em
   **LIBERAR NO FIREWALL** (pede a senha) ou rode no terminal, trocando pela sua rede:
   `sudo ufw allow from 192.168.1.0/24 to any port 7099:7118 proto tcp comment "Arasaka Uplink"`.
   O instalador também faz isso (pedindo a senha) quando o firewall está ligado.
2. **Mesma rede:** o PC no cabo e o celular no Wi-Fi funcionam juntos se estiverem no mesmo roteador. Não funciona se o
   celular estiver na **rede de convidados** ou num roteador/repetidor com outra faixa de endereços (o começo do IP do
   celular, em Configurações > Wi-Fi > detalhes, deve ser o mesmo do endereço que aparece no Uplink, ex.: `192.168.1.`).
3. **Isolamento do Wi-Fi:** alguns roteadores têm "isolamento de cliente/AP" ligado, que impede o Wi-Fi de falar com
   os aparelhos do cabo. Desligue nas configurações do roteador.

## Instalar

Pela **Arasaka Central** (Loja → Apps), ou:

```bash
./install.sh
```

Rode **sem sudo**. Para remover: `./uninstall.sh`.

---

Arasaka é marca da CD PROJEKT RED (projeto de fã, sem fins comerciais). A fonte `cedge1` usa a licença
FontStruct Non-Commercial.
