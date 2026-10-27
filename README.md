# VistaTube

VistaTube é um cliente alternativo para vídeos do YouTube no Android, baseado no [LibreTube v32.1](https://github.com/libre-tube/LibreTube).

## Prévia 0.1.0

- Nome e identificador de aplicação independentes (`app.vistatube.mobile.debug` na prévia).
- Tema escuro azul/ciano, ícone vetorial e marca VistaTube.
- Reprodução, pesquisa, canais, playlists, subscrições, legendas, PiP, downloads e SponsorBlock herdados do LibreTube.
- Android 8.0+; Kotlin/Material 3 Expressive.

**Esta variante ainda precisa de compilação e testes em dispositivos reais.** Sem login de conta Google e sem suporte Cast específico do VistaTube. Algumas funcionalidades podem falhar com alterações no YouTube.

## Download e código-fonte

O workflow GitHub Actions `Build VistaTube APK and GitHub Release` compila o APK de testes e cria automaticamente [Releases](https://github.com/yuregabriell/VistaTube/releases) com:

- `VistaTube-preview-N.apk` — prévia Android assinada com chave debug.
- `VistaTube-source-N.tar.gz` — cópia completa do código-fonte transformado, com licenças e atribuições.
- `SHA256SUMS.txt` — checksums dos artefactos.

**Atenção:** cada build debug pode usar uma chave de assinatura diferente, pelo que atualizar uma instalação anterior pode exigir desinstalação (e perder dados locais). Para lançamentos estáveis precisamos de uma chave de assinatura persistente em GitHub Secrets.

## Compilar localmente

```sh
git clone --depth 1 --branch v32.1 https://github.com/libre-tube/LibreTube.git upstream
python3 scripts/brand.py upstream
cd upstream
./gradlew :app:assembleDebug
```

Requisitos: Java 17, Android SDK 36 e rede. O workflow valida o SHA de origem `6a861f4282c3de73b840793365d8ac7114b5a80f`.

## Licenciamento

O VistaTube é uma modificação não oficial do LibreTube e mantém a licença **GPL-3.0-or-later**. Atribuição ao [LibreTube](https://github.com/libre-tube/LibreTube) e aos respetivos contribuidores. Não existe associação oficial à Google, ao YouTube ou à equipa do LibreTube.

## Futuro

Interface de descoberta mais personalizada, releases assinados de forma persistente, Cast e experiência Android TV.
