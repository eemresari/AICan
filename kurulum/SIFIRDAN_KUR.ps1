<#
    AICAN — SIFIRDAN KURULUM  (yeni sergi PC'si icin tek dosya)
    ============================================================

    Yeni, HIC DOKUNULMAMIS bir Windows 11 makinesinde calisir. Projenin
    kendisi bile makinede olmadan baslar: git + Python'u kurar, depoyu
    klonlar, sonra kurulum\KUR.bat'i cagirir (Ollama, model, Whisper,
    bagimliliklar, kisayol, saglik kontrolu onun isi).

    KULLANIM — yeni PC'de PowerShell'i YONETICI olarak ac ve:

        Set-ExecutionPolicy -Scope Process Bypass -Force
        .\SIFIRDAN_KUR.ps1

    Bu dosyayi USB ile tasi (ya da depodan tek dosya indir). Baska hicbir
    sey tasimana gerek yok — TEK istisna ses onbellegi, bkz. asagida.

    ELDEN TASINMASI GEREKEN TEK SEY: orchestrator/tts/cache  (~830 MB)
    ElevenLabs ile uretilmis hazir sesler; .gitignore'da oldugu icin klonla
    GELMEZ. Eski PC'de  `python -m tts.paket_hazirla --kopyala`  ile paketle,
    USB ile tasi. Tasinmazsa oyun yine calisir ama replikler canli
    sentezlenir (kredi + gecikme) ya da ucretsiz sese duser.

    Parametreler:
      -Hedef  <yol>   proje nereye klonlansin      (varsayilan C:\aican)
      -Dal    <ad>    hangi git dali              (varsayilan sergi-pc-rtx5090)
      -Anahtar <key>  ElevenLabs API anahtari     (opsiyonel)
      -Sessiz         KUR.bat'a soru sordurma
#>
param(
    [string]$Hedef   = "C:\aican",
    [string]$Dal     = "sergi-pc-rtx5090",
    [string]$Depo    = "https://github.com/atlamayanat/AICan.git",
    [string]$Anahtar = "",
    [switch]$Sessiz
)

$ErrorActionPreference = "Stop"
$adim = 0
function Baslik($ad) {
    $script:adim++
    Write-Host ""
    Write-Host ("=== [{0}] {1} " -f $script:adim, $ad).PadRight(60, "=") -ForegroundColor Cyan
}
function Bilgi($m)  { Write-Host "  $m" }
function Uyari($m)  { Write-Host "  !! $m" -ForegroundColor Yellow }
function Olumlu($m) { Write-Host "  $m" -ForegroundColor Green }

Write-Host ""
Write-Host "  ==============================================" -ForegroundColor Cyan
Write-Host "    AICAN — SIFIRDAN SERGI PC KURULUMU"          -ForegroundColor Cyan
Write-Host "  ==============================================" -ForegroundColor Cyan
Write-Host "    Hedef : $Hedef"
Write-Host "    Dal   : $Dal"
Write-Host "    Bu islem internet ister ve ~30-60 dk surer."
Write-Host ""

# ——— 1. winget var mi? ————————————————————————————————————————
Baslik "Paket yoneticisi (winget)"
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Uyari "winget bulunamadi. Windows 11'de 'App Installer' Microsoft Store'dan kurulmali:"
    Bilgi "https://apps.microsoft.com/detail/9nblggh4nns1"
    Bilgi "Kurduktan sonra bu betigi tekrar calistir."
    exit 1
}
Olumlu "winget hazir."

# ——— 2. Git ————————————————————————————————————————————————
Baslik "Git"
if (Get-Command git -ErrorAction SilentlyContinue) {
    Olumlu ("Zaten kurulu: " + (git --version))
} else {
    Bilgi "Kuruluyor (winget)..."
    winget install -e --id Git.Git --accept-source-agreements --accept-package-agreements
    # winget yeni PATH'i BU pencereye yansitmaz — makine+kullanici PATH'ini tazele.
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Uyari "Git kuruldu ama bu pencerede gorunmuyor. PowerShell'i KAPAT, yeniden ac,"
        Bilgi "betigi tekrar calistir."
        exit 1
    }
    Olumlu ("Kuruldu: " + (git --version))
}

# ——— 3. Python ————————————————————————————————————————————
Baslik "Python 3.13"
if (Get-Command python -ErrorAction SilentlyContinue) {
    Olumlu ("Zaten kurulu: " + (python --version))
} else {
    Bilgi "Kuruluyor (winget)..."
    winget install -e --id Python.Python.3.13 --accept-source-agreements --accept-package-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        Uyari "Python kuruldu ama bu pencerede gorunmuyor. PowerShell'i KAPAT, yeniden ac,"
        Bilgi "betigi tekrar calistir."
        exit 1
    }
    Olumlu ("Kuruldu: " + (python --version))
}

# ——— 4. NVIDIA surucusu ————————————————————————————————————
Baslik "Ekran karti"
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    $g = (nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader) | Select-Object -First 1
    Olumlu "GPU: $g"
    # RTX 50 serisi (Blackwell) CUDA 12.8 ister; o da >= 570 surucu demek.
    $surucu = [double](($g -split ",")[2].Trim() -replace "[^\d.].*$", "")
    if ($g -match "RTX\s*50[6-9]0" -and $surucu -lt 570) {
        Uyari "Surucu $surucu — RTX 50 serisi icin >= 570 gerekli (CUDA 12.8)."
        Bilgi "Guncelle: https://www.nvidia.com/download/index.aspx  (sonra betigi tekrar calistir)"
    }
} else {
    Uyari "nvidia-smi yok — NVIDIA surucusu kurulu degil."
    Bilgi "Sergi PC'sinde ONCE surucuyu kur: https://www.nvidia.com/download/index.aspx"
    Bilgi "Surucusuz devam edersen LLM ve ses tanima CPU'da calisir (cok yavas)."
    if (-not $Sessiz) {
        $c = Read-Host "  Yine de devam edeyim mi? (e/h)"
        if ($c -notmatch "^[eEyY]") { exit 1 }
    }
}

# ——— 5. Depoyu getir ————————————————————————————————————————
Baslik "AICAN deposu"
if (Test-Path (Join-Path $Hedef ".git")) {
    Bilgi "Depo zaten var — guncelleniyor."
    git -C $Hedef fetch origin
    git -C $Hedef checkout $Dal
    git -C $Hedef pull --ff-only origin $Dal
    Olumlu "Guncel: $Hedef ($Dal)"
} else {
    if ((Test-Path $Hedef) -and (Get-ChildItem $Hedef -Force | Measure-Object).Count -gt 0) {
        Uyari "$Hedef dolu ama git deposu degil. Baska bir -Hedef ver ya da klasoru bosalt."
        exit 1
    }
    Bilgi "Klonlaniyor: $Depo ($Dal)"
    Bilgi "(Depo ozelse GitHub kullanici adi/parola penceresi acilacak — PAT gir.)"
    git clone --branch $Dal --single-branch $Depo $Hedef
    if ($LASTEXITCODE -ne 0) {
        Uyari "Klonlama basarisiz. Ozel depoysa GitHub hesabinla yetkilendirmen gerekiyor."
        exit 1
    }
    Olumlu "Klonlandi: $Hedef"
}

# ——— 6. KUR.bat ————————————————————————————————————————————
Baslik "Ana kurulum (KUR.bat)"
$kur = Join-Path $Hedef "kurulum\KUR.bat"
if (-not (Test-Path $kur)) {
    Uyari "$kur bulunamadi — depo eksik klonlanmis."
    exit 1
}
$argv = @()
if ($Sessiz)  { $argv += "--sessiz" }
if ($Anahtar) { $argv += @("--anahtar", $Anahtar) }
Bilgi "Calistiriliyor: $kur $argv"
& $kur @argv
$sonuc = $LASTEXITCODE

# ——— 7. Ozet ————————————————————————————————————————————————
Baslik "Ozet"
if ($sonuc -eq 0) {
    Olumlu "KURULUM TAMAM."
} else {
    Uyari "KUR.bat hata ile bitti (kod $sonuc) — yukaridaki saglik kontrolu satirlarina bak."
}
Write-Host ""
Bilgi "GERIYE KALAN TEK IS — ses onbellegi (git'te YOK, ~830 MB):"
Bilgi "  1) ESKI PC'de:  cd orchestrator; python -m tts.paket_hazirla --kopyala"
Bilgi "  2) olusan sergi_paketi\cache\  icerigini USB ile tasi ve suraya kopyala:"
Bilgi "     $Hedef\orchestrator\tts\cache\"
Bilgi "  3) Dogrula:  cd $Hedef\orchestrator; python -m tts.gen_batch_elevenlabs --eksik"
Bilgi "     EKSIK = 0 gormelisin."
Write-Host ""
Bilgi "Baslatmak icin: masaustundeki 'AICAN Baslat' kisayolu"
Bilgi "Tekrar kontrol:  python $Hedef\kurulum\saglik_kontrol.py"
Write-Host ""
exit $sonuc
