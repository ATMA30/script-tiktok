import os


def trouver_dernier_projet():
    forced = os.environ.get("FORCE_PROJET")
    if forced and os.path.isdir(forced):
        return forced
    if not os.path.isdir("projets"):
        return None
    dossiers = [
        os.path.join("projets", d)
        for d in os.listdir("projets")
        if os.path.isdir(os.path.join("projets", d))
    ]
    return max(dossiers, key=os.path.getmtime) if dossiers else None
