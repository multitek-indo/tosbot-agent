# Private document assets

No logo, signature, real invoice, offer, bank account, or customer document is distributed in this public repository.

On the VPS, provision private files directly into `/opt/tosbot-ai/assets/` **after** installing:

```bash
sudo install -o root -g root -m 0644 /path/to/private/logo.png /opt/tosbot-ai/assets/logo.png
sudo install -o root -g root -m 0644 /path/to/private/offer-signature.png /opt/tosbot-ai/assets/offer-signature.png
```

Do not put these images in Git, GitHub Actions artifacts, or a public release ZIP. Invoice generation supports a missing logo, but offer PDF generation intentionally fails if the signature image is absent, instead of silently omitting a required signature. For the existing VPS, the installer preserves files already present under `/opt/tosbot-ai/assets/`.
