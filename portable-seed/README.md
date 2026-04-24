# Portable Seed

This directory is for private release seed data only.

Place a local encrypted `proxyvault.db` here before building a private release if the app must start with preloaded profiles.

Recommended developer flow:

```powershell
python .\tools\create_portable_seed.py --force
```

If the old plaintext seed still exists in the current Git commit but was removed from the working tree, use:

```powershell
python .\tools\create_portable_seed.py --from-git-head --force
```

Do not place QR files in this directory. QR images contain the same secrets as the profiles and are not protected by the master password.

Do not commit real profile databases or generated QR files.
