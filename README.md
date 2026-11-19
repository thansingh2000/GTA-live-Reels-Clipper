# GTA Live → 9:16 Reels Clipper

YouTube live (ya normal video) ka link daalo — tool stream ko record karke har N second ki **1080x1920 (9:16) reel clips** banata hai aur browser me apne aap download karta jaata hai.

## Requirements

- Windows 10/11
- [Python 3.10+](https://www.python.org/downloads/) (install karte waqt **"Add Python to PATH"** tick karna)
- [Node.js](https://nodejs.org/) (recommended — YouTube ke saare formats ke liye yt-dlp isko use karta hai)
- Koi browser jisme **YouTube login** ho (is PC par **Brave** kaam karta hai)

`ffmpeg` alag se install karne ki zarurat nahi — `imageio-ffmpeg` package apne saath laata hai.

## Setup + Run (aasan tarika)

`start.bat` par double-click karo. Ye:

1. `venv` bana dega (pehli baar)
2. Saari dependencies install / update karega
3. Server start karke browser me http://127.0.0.1:5000 khol dega

## Setup + Run (manual)

```powershell
cd d:\tool
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
pip install -U "yt-dlp[default]"
python app.py
```

Phir browser me kholo: http://127.0.0.1:5000

## Use kaise karein

1. YouTube live link paste karo.
2. **Clip length** chuno (15–90 sec).
3. **9:16 Style** chuno:
   - **Full gameplay + blur background** — poora gameplay beech me, upar-neeche blur (reels ke liye best)
   - **Center crop** — beech ka hissa full screen
   - **Zoom fill** — frame zoom karke screen bhar do
4. **Source quality** — PC slow ho to 720p lo.
5. **YouTube cookies** — "Auto" rehne do; tool khud browser dhoondh lega.
6. **Start** dabao. Har clip bante hi UI me preview aayega aur auto-download hoga.
   - Pehli baar browser "multiple downloads" ki permission maangega → **Allow** karo.
7. **Stop** dabane par chalu clip bhi save hokar band hoga.

Saari clips yahan bhi save hoti hain:

```
d:\tool\clips\<date_time>_<stream_title>\clip_0000.mp4, clip_0001.mp4, ...
```

UI me **📁 Folder kholo** button se seedha khul jaata hai.

## Problems aur solution

| Problem | Solution |
| --- | --- |
| `Sign in to confirm you're not a bot` | Browser me YouTube login karo aur cookies "Auto"/Brave rakho. Phir bhi na chale to neeche `cookies.txt` wala tarika use karo. |
| `Could not copy Chrome cookie database` | Chrome/Edge ki cookies yt-dlp nahi padh paata. Brave ya Firefox use karo, ya `cookies.txt`. |
| Log me `speed=` 1x se kam | PC live se peeche hai — quality 720p karo ya "Center crop" style lo. |
| Stream ruk gaya | Tool 5 second me khud reconnect karta hai, numbering wahi se continue hoti hai. |
| YouTube extraction error achanak aane lage | `.\venv\Scripts\pip install -U "yt-dlp[default]"` chalao (ya bas `start.bat` dubara chalao). |

### cookies.txt tarika

1. Browser me "Get cookies.txt LOCALLY" extension install karo.
2. youtube.com kholo (login ke saath) aur cookies export karo.
3. File ko `d:\tool\cookies.txt` naam se save karo — tool isko apne aap use karega.

## Project structure

```
d:\tool
├── app.py              # Flask backend: yt-dlp + ffmpeg recording / clipping
├── templates\index.html# Web UI
├── requirements.txt
├── start.bat           # One-click setup + run
└── clips\              # Bani hui reels
```
