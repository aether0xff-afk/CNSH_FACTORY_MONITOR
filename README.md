# Factory Monitor v0.1 — Minecraft Java 26.3 / Windows + Fabric

**기능:** 10초마다 RCON으로 등록된 상자/호퍼 `Items` 확인 → SQLite 저장 → 인증된 웹 대시보드에서 조회. 공장 등록, 재고, 관측 순유입·순유출, 속도, 재고 그래프, 최근 이벤트가 포함됩니다.

> **정확도:** 이 시스템은 입출고 이벤트 자체를 추적하지 않습니다. `+20개 생산 / -64개 반출`이 한 표본 구간에 동시에 일어나면 `-44개`로 기록됩니다. 표기되는 유입/유출은 **관측된 순재고 변화의 양/음 분리**입니다. 청크 언로드/조회 실패 때는 재고 0으로 기록하지 않으며, 실패 직후 첫 성공 표본에서도 변화량을 계산하지 않습니다.

## 1. Windows 마인크래프트 서버 컴퓨터에서 설치

PowerShell에서 압축을 푼 디렉터리로 이동:

```powershell
cd C:\CNSH_FACTORY_MONITOR
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1
notepad .env
```

`.env`에서 다음을 반드시 변경합니다:

- `RCON_HOST=127.0.0.1` — **서버 컴퓨터 자체에서 실행할 때** 설정입니다. VPN IP가 아니라 로컬 주소입니다.
- `RCON_PORT=25575`
- `RCON_PASSWORD=` — 실제 `server.properties`에 설정된 RCON 비밀번호
- `FM_USER=admin` — 사이트 로그인 ID
- `FM_PASSWORD=` — 사이트만의 별도 강력한 비밀번호 (12자 이상)

비밀번호와 `*.env` 파일을 다른 사람에게 공유하지 마세요.

```powershell
.\start_server.cmd
```

접속: **http://127.0.0.1:8000** (브라우저에서 사이트 계정 입력)

설치 스크립트는 프로젝트 폴더에 `.conda` 전용 Conda 환경(Python 3.13)을 만들고 라이브러리를 설치합니다. Windows `py` 런처나 별도의 `venv`가 필요하지 않습니다. `start_server.cmd`는 해당 환경의 `python.exe`를 직접 실행하므로 Windows 작업 스케줄러에서도 Conda 활성화가 필요 없습니다. 기존 `.env`와 `factories.json`은 재설치해도 보존됩니다.

설치 스크립트가 `factories.example.json`에서 개인 설정 파일 `factories.json`을 생성합니다. **실제 서버 상자 좌표로 수정한 다음** 첫 실행을 하세요. 이후 첫 실행 시 등록된 공장이 자동으로 DB에 추가됩니다. 이후 웹의 **공장 등록** 버튼에서 공장을 추가할 수 있습니다. SQLite DB는 `data/factory.db`로 저장되며 앱을 재시작해도 보존됩니다.

예제 `factories.example.json`에는 **가상의 상자 좌표** `(100, 64, 200)` / `(101, 64, 200)`이 들어 있습니다. 반드시 서버의 실제 좌표로 교체하세요. 실좌표를 포함하는 `factories.json`은 Git 추적에서 제외됩니다.

초기 등록 완료 뒤에는 `factories.json`을 수정해도 DB에 자동 반영되지 않습니다. 추가 공장은 웹 UI에서 등록하세요.

## 2. 확인하기

다른 PowerShell에서:

```powershell
curl.exe -u admin http://127.0.0.1:8000/api/factories
```

비밀번호를 요구하면 사이트의 `FM_PASSWORD`를 입력하면 됩니다. 서버 로그는 `logs/server.log`에 저장됩니다.

데이터가 `조회 오류`라면 다음을 점검하세요.
- RCON이 Minecraft 서버 재시작 후 활성화되었는지
- 서버가 실행되고 있는지
- 상자 좌표가 정확한지
- 상자 청크가 로딩되어 있는지 (봇이 적절한 AFK 위치에 있을 때 조회 가능)

이 수집기는 `/forceload`를 자동 실행하지 않으며, 세계를 변경하지 않습니다.

## 3. Cloudflare Quick Tunnel — 외부 테스트

[공식 Cloudflare cloudflared 다운로드](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)로 Windows용 `cloudflared.exe`를 설치한 후, **서버 컴퓨터**의 PowerShell에서:

```powershell
cloudflared tunnel --url http://127.0.0.1:8000 --allowed-mail your-email@example.com
```

`your-email@example.com`을 본인 이메일로 바꾸세요. Cloudflare는 임시 `https://...trycloudflare.com` URL을 출력합니다. 접속자는 이메일 일회용 PIN + 사이트 비밀번호를 거쳐야 합니다. 이 URL은 터널 프로세스가 종료되면 사용할 수 없습니다.

Quick Tunnel은 개발·테스트용입니다. 정식 24시간 운영은 아래의 고정 Tunnel을 사용하세요.

## 4. Cloudflare 고정 Tunnel — 24시간 배포

Cloudflare에서 관리하는 도메인이 있어야 고정된 사용자 지정 호스트 이름을 사용하기 편합니다.

1. [Cloudflare Zero Trust](https://one.dash.cloudflare.com/) → **Networks / Connectors / Cloudflare Tunnels**에서 **Create tunnel** (Cloudflared 유형)
2. `factory-monitor` 같은 이름 지정 후 Windows 선택
3. 화면에 표시된 `cloudflared.exe service install <TOKEN>` 명령을 **서버 컴퓨터 관리자 PowerShell**에서 실행합니다. 토큰은 비밀이므로 저장소/대화에 올리지 마세요.
4. Tunnel에 **Public hostname / Published application** 추가. Hostname 예: `factory.example.com`, 서비스 URL: **`http://127.0.0.1:8000`**
5. Cloudflare **Zero Trust → Access → Applications → Add self-hosted application**: `factory.example.com`을 지정, **Allow 정책에 본인 이메일만 등록**합니다.
6. 스마트폰 모바일 데이터에서 `https://factory.example.com` 접속 테스트

**중요:** 사이트 URL을 다른 사람에게 공개하기 전에 Access 정책 적용 여부를 확인하세요. 이 프로젝트는 사이트 자체에도 HTTP Basic 인증을 추가했습니다.

고정 터널 연결은 Cloudflare가 서버로 아웃바운드 연결을 생성하므로, 공유기에서 `8000` 포트를 포워딩하지 않습니다.

## 5. PowerShell을 닫아도 계속 실행 — Windows 자동 시작

서버 컴퓨터 **관리자 PowerShell**에서 실행합니다. 기존에 수동으로 실행한 `start_server.cmd`가 있다면 먼저 `Ctrl+C`로 중지하세요.

```powershell
cd C:\CNSH_FACTORY_MONITOR
git pull
powershell -ExecutionPolicy Bypass -File .\install_background.ps1
```

이 명령은 **CNSH Factory Monitor** 작업을 Windows 작업 스케줄러에 등록합니다. 컴퓨터 시작 시 SYSTEM 계정으로 백그라운드 실행되므로 로그인이나 PowerShell 창이 필요 없습니다. 실패하면 최대 3번 재시도하며 실행 시간 제한은 해제됩니다. Python은 저장소의 `.conda\python.exe`를 사용하고 로그는 기존 `logs\server.log`에 기록됩니다.

> 기존 수동 실행 서버가 8000번 포트를 사용하고 있다면 프로세스를 강제 종료하지 않습니다. 작업은 등록되지만 실행되지 않으므로, 기존 창에서 `Ctrl+C`로 서버를 종료하고 아래 명령을 실행하세요.

```powershell
Start-ScheduledTask -TaskName "CNSH Factory Monitor"
```

상태 확인:

```powershell
Get-ScheduledTask -TaskName "CNSH Factory Monitor"
Test-NetConnection 127.0.0.1 -Port 8000
Get-Content C:\CNSH_FACTORY_MONITOR\logs\server.log -Tail 30
```

제어 방법 (관리자 PowerShell):

```powershell
Stop-ScheduledTask -TaskName "CNSH Factory Monitor"
Start-ScheduledTask -TaskName "CNSH Factory Monitor"
# 자동 시작을 제거하려면:
Unregister-ScheduledTask -TaskName "CNSH Factory Monitor" -Confirm:$false
```

이 작업은 Python 웹서버와 데이터 수집기만 자동 실행합니다. Minecraft 서버 및 `cloudflared` Windows 서비스는 별도로 실행해야 합니다. Windows가 꺼져 있거나 절전 상태면 웹서버도 작동하지 않습니다.

## 6. 백업 / 보안

- **백업 대상:** `data/factory.db`(실행 중 백업은 SQLite Backup API 권장), `.env`(비밀이므로 별도 보안 저장), 그리고 `factories.json` (개인 설정, 공개 금지).
- **절대 공개 금지:** RCON TCP 25575, `.env`, Cloudflare 터널 설치 토큰.
- 서버 URL과 브라우저의 API로는 RCON 명령어를 실행할 수 없습니다. 수집 명령어가 코드에서 정해져 있습니다.
- 서버가 켜져 있어도 **크리퍼 생산은 플레이어나 적절한 Carpet 가짜 플레이어가 활성화되어 있어야** 진행됩니다.
- 공장 상자 2개는 가능하면 한 청크/적절한 로딩 상태에 두세요.
- 백엔드는 `127.0.0.1:8000`에만 바인딩합니다. VPN으로 로컬 브라우저 대신 원격 확인할 경우 터널을 사용하세요.
- **추후 개선:** 호퍼 이동 이벤트 계측용 서버 모드를 추가하면 진짜 개별 입출고 이벤트를 얻을 수 있습니다.

## API

- `GET /api/factories` — 공장 카드 상태, 10분/1시간 순변화
- `POST /api/factories` — 공장 등록
- `PATCH /api/factories/{id}/enabled?enabled=false` — 수집 일시정지
- `GET /api/factories/{id}/history?hours=24` — 그래프용 재고 표본, 최근 변화 이벤트

모든 엔드포인트와 정적 웹사이트는 HTTP Basic 인증이 필요합니다.

## GitHub 배포 관련

공개 저장소에는 비밀번호와 실제 서버 좌표를 올리지 마세요. `.env`, `factories.json`, `.conda/`, `data/`, `logs/`는 `.gitignore`로 제외됩니다. 클론 후 `setup_windows.ps1`로 개인 설정 파일을 만들고 실제 좌표/암호를 설정하세요.