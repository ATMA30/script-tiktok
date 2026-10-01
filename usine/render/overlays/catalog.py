"""Catalogue des familles d'overlays : métadonnées, durées, rotation des variantes, planning."""

SEMANTIC_ANIMATION_TYPES = [
    "map_zoom",
    "message_send",
    "phone_call",
    "email_sent",
    "cctv_scan",
    "file_open",
    "redacted_report",
    "year_marker",
    "timeline_pin",
    "counter",
    "missing_person",
    "search_grid",
    "evidence_photo",
    "fingerprint_scan",
    "audio_waveform",
    "radio_signal",
    "police_lights",
    "route_trace",
    "door_open",
    "key_object",
    "medical_scan",
    "lab_sample",
    "newspaper_clip",
    "court_record",
    "classified_stamp",
    "entity_radar",
    "weather_alert",
    "storm_warning",
    "footprint_trail",
    "blood_trace",
    "fire_burst",
    "smoke_fog",
    "underground_depth",
    "coordinates_lock",
    "interrogation_note",
    "witness_card",
    "clock_tick",
    "warning_flash",
    "archive_box",
    "question_prompt",
]

SEMANTIC_ANIMATION_TYPES.extend(
    [
        "true_story_card",
        "last_seen_marker",
        "floor_plan",
        "exit_scan",
        "blind_spot",
        "corridor_scan",
        "motion_detector",
        "security_log",
        "missing_poster",
        "family_photo",
        "witness_quote",
        "case_board",
        "evidence_thread",
        "theory_stack",
        "official_denial",
        "document_leak",
        "breaking_news",
        "calendar_flip",
        "time_jump",
        "timeline_split",
        "mind_control",
        "memory_flash",
        "experiment_chamber",
        "thermal_scan",
        "dna_spiral",
        "heartbeat_monitor",
        "voice_print",
        "signal_jammer",
        "satellite_sweep",
        "map_pin_drop",
        "proximity_alert",
        "power_cut",
        "neon_bar",
        "searchlight",
        "basement_elevator",
        "sealed_door",
        "archive_stamp",
        "object_isolate",
        "crowd_noise",
        "room_tone",
    ]
)

SEMANTIC_META = {
    "map_zoom": {
        "label": "LOCALISATION",
        "detail": "Zoom satellite",
        "icon": "pin",
        "family": "map",
    },
    "message_send": {
        "label": "MESSAGE SORTANT",
        "detail": "Texte saisi puis envoyé",
        "icon": "radio",
        "family": "message",
    },
    "phone_call": {
        "label": "APPEL TRACE",
        "detail": "Signal téléphonique",
        "icon": "radio",
        "family": "signal",
    },
    "email_sent": {
        "label": "EMAIL EXPÉDIÉ",
        "detail": "Transmission numérique",
        "icon": "file",
        "family": "card",
    },
    "cctv_scan": {
        "label": "CAMÉRA ACTIVE",
        "detail": "Analyse de surveillance",
        "icon": "eye",
        "family": "scan",
    },
    "file_open": {
        "label": "DOSSIER OUVERT",
        "detail": "Pièces indexées",
        "icon": "file",
        "family": "file",
    },
    "redacted_report": {
        "label": "RAPPORT CAVIARDÉ",
        "detail": "Noms supprimés",
        "icon": "lock",
        "family": "redacted",
    },
    "year_marker": {
        "label": "DATE CLÉ",
        "detail": "Ancrage chronologique",
        "icon": "file",
        "family": "year",
    },
    "timeline_pin": {
        "label": "TIMELINE",
        "detail": "Événement verrouillé",
        "icon": "pin",
        "family": "card",
    },
    "counter": {
        "label": "COMPTEUR",
        "detail": "Volume détecté",
        "icon": "warning",
        "family": "counter",
    },
    "missing_person": {
        "label": "DISPARITION",
        "detail": "Avis de recherche",
        "icon": "eye",
        "family": "card",
    },
    "search_grid": {
        "label": "RECHERCHE",
        "detail": "Quadrillage de zone",
        "icon": "eye",
        "family": "search",
    },
    "evidence_photo": {
        "label": "PREUVE PHOTO",
        "detail": "Image cataloguée",
        "icon": "file",
        "family": "file",
    },
    "fingerprint_scan": {
        "label": "EMPREINTE",
        "detail": "Scan biométrique",
        "icon": "eye",
        "family": "scan",
    },
    "audio_waveform": {
        "label": "SIGNAL AUDIO",
        "detail": "Forme d'onde isolée",
        "icon": "radio",
        "family": "signal",
    },
    "radio_signal": {
        "label": "SIGNAL RADIO",
        "detail": "Fréquence interceptée",
        "icon": "radio",
        "family": "signal",
    },
    "police_lights": {
        "label": "POLICE",
        "detail": "Intervention en cours",
        "icon": "warning",
        "family": "card",
    },
    "route_trace": {
        "label": "TRAJET",
        "detail": "Itinéraire reconstruit",
        "icon": "pin",
        "family": "route",
    },
    "door_open": {
        "label": "PORTE",
        "detail": "Point de passage",
        "icon": "lock",
        "family": "card",
    },
    "key_object": {
        "label": "OBJET CLÉ",
        "detail": "Élément isolé",
        "icon": "file",
        "family": "card",
    },
    "medical_scan": {
        "label": "ANALYSE MÉDICALE",
        "detail": "Données biologiques",
        "icon": "warning",
        "family": "scan",
    },
    "lab_sample": {
        "label": "ÉCHANTILLON",
        "detail": "Protocole laboratoire",
        "icon": "file",
        "family": "card",
    },
    "newspaper_clip": {
        "label": "PRESSE",
        "detail": "Coupure archivée",
        "icon": "file",
        "family": "file",
    },
    "court_record": {
        "label": "PROCÈS-VERBAL",
        "detail": "Document légal",
        "icon": "file",
        "family": "file",
    },
    "classified_stamp": {
        "label": "CLASSIFIÉ",
        "detail": "Accès restreint",
        "icon": "lock",
        "family": "stamp",
    },
    "entity_radar": {
        "label": "SIGNATURE INCONNUE",
        "detail": "Présence non identifiée",
        "icon": "radio",
        "family": "radar",
    },
    "weather_alert": {
        "label": "MÉTÉO",
        "detail": "Condition relevée",
        "icon": "warning",
        "family": "card",
    },
    "storm_warning": {
        "label": "ALERTE ORAGE",
        "detail": "Pression instable",
        "icon": "warning",
        "family": "card",
    },
    "footprint_trail": {
        "label": "TRACES",
        "detail": "Empreintes relevées",
        "icon": "pin",
        "family": "route",
    },
    "blood_trace": {
        "label": "TRACE BIO",
        "detail": "Marque organique",
        "icon": "warning",
        "family": "card",
    },
    "fire_burst": {
        "label": "INCENDIE",
        "detail": "Source thermique",
        "icon": "warning",
        "family": "card",
    },
    "smoke_fog": {
        "label": "BROUILLARD",
        "detail": "Visibilité réduite",
        "icon": "eye",
        "family": "card",
    },
    "underground_depth": {
        "label": "SOUS-SOL",
        "detail": "Profondeur estimée",
        "icon": "lock",
        "family": "depth",
    },
    "coordinates_lock": {
        "label": "COORDONNÉES",
        "detail": "Position verrouillée",
        "icon": "pin",
        "family": "card",
    },
    "interrogation_note": {
        "label": "INTERROGATOIRE",
        "detail": "Déclaration analysée",
        "icon": "file",
        "family": "card",
    },
    "witness_card": {
        "label": "TÉMOIN",
        "detail": "Identité indexée",
        "icon": "eye",
        "family": "card",
    },
    "clock_tick": {
        "label": "HORLOGE",
        "detail": "Minute critique",
        "icon": "warning",
        "family": "clock",
    },
    "warning_flash": {
        "label": "ALERTE",
        "detail": "Risque élevé",
        "icon": "warning",
        "family": "card",
    },
    "archive_box": {
        "label": "ARCHIVE",
        "detail": "Boîte scellée",
        "icon": "file",
        "family": "file",
    },
    "question_prompt": {
        "label": "QUESTION",
        "detail": "Hypothèse ouverte",
        "icon": "warning",
        "family": "question",
    },
}

SEMANTIC_META.update(
    {
        "true_story_card": {
            "label": "HISTOIRE VRAIE",
            "detail": "Lieux et témoins réels",
            "icon": "eye",
            "family": "truth",
        },
        "last_seen_marker": {
            "label": "DERNIÈRE IMAGE",
            "detail": "Dernier moment confirmé",
            "icon": "eye",
            "family": "poster",
        },
        "floor_plan": {
            "label": "PLAN DES LIEUX",
            "detail": "Pièce par pièce",
            "icon": "file",
            "family": "blueprint",
        },
        "exit_scan": {
            "label": "SORTIE CONTRÔLÉE",
            "detail": "Passage vérifié",
            "icon": "lock",
            "family": "blueprint",
        },
        "blind_spot": {
            "label": "ANGLE MORT",
            "detail": "Zone non filmée",
            "icon": "eye",
            "family": "blueprint",
        },
        "corridor_scan": {
            "label": "COULOIR",
            "detail": "Trajectoire analysée",
            "icon": "pin",
            "family": "blueprint",
        },
        "motion_detector": {
            "label": "MOUVEMENT",
            "detail": "Détection instable",
            "icon": "eye",
            "family": "scan",
        },
        "security_log": {
            "label": "JOURNAL CAMÉRA",
            "detail": "Entrée horodatée",
            "icon": "file",
            "family": "scan",
        },
        "missing_poster": {
            "label": "AVIS DE RECHERCHE",
            "detail": "Personne introuvable",
            "icon": "eye",
            "family": "poster",
        },
        "family_photo": {
            "label": "FAMILLE",
            "detail": "Impact humain",
            "icon": "eye",
            "family": "poster",
        },
        "witness_quote": {
            "label": "TÉMOIGNAGE",
            "detail": "Déclaration clé",
            "icon": "file",
            "family": "caseboard",
        },
        "case_board": {
            "label": "TABLEAU D'ENQUÊTE",
            "detail": "Liens et hypothèses",
            "icon": "file",
            "family": "caseboard",
        },
        "evidence_thread": {
            "label": "FIL D'INDICES",
            "detail": "Éléments reliés",
            "icon": "pin",
            "family": "caseboard",
        },
        "theory_stack": {
            "label": "THÉORIES",
            "detail": "Pistes contradictoires",
            "icon": "warning",
            "family": "caseboard",
        },
        "official_denial": {
            "label": "DÉMENTI OFFICIEL",
            "detail": "Version contestée",
            "icon": "lock",
            "family": "caseboard",
        },
        "document_leak": {
            "label": "FUITE DOCUMENT",
            "detail": "Pièce sortie du dossier",
            "icon": "file",
            "family": "news",
        },
        "breaking_news": {
            "label": "ALERTE PRESSE",
            "detail": "Article archivé",
            "icon": "file",
            "family": "news",
        },
        "calendar_flip": {
            "label": "DATE",
            "detail": "Repère temporel",
            "icon": "file",
            "family": "year",
        },
        "time_jump": {
            "label": "ELLIPSE",
            "detail": "Des années passent",
            "icon": "warning",
            "family": "year",
        },
        "timeline_split": {
            "label": "TIMELINE BRISÉE",
            "detail": "Deux versions possibles",
            "icon": "pin",
            "family": "year",
        },
        "mind_control": {
            "label": "CONTRÔLE MENTAL",
            "detail": "Influence psychique",
            "icon": "radio",
            "family": "experiment",
        },
        "memory_flash": {
            "label": "MÉMOIRE",
            "detail": "Souvenir fragmenté",
            "icon": "eye",
            "family": "experiment",
        },
        "experiment_chamber": {
            "label": "PROTOCOLE",
            "detail": "Expérience clandestine",
            "icon": "file",
            "family": "experiment",
        },
        "thermal_scan": {
            "label": "THERMIQUE",
            "detail": "Source chaude isolée",
            "icon": "warning",
            "family": "experiment",
        },
        "dna_spiral": {
            "label": "ADN",
            "detail": "Trace biologique",
            "icon": "warning",
            "family": "experiment",
        },
        "heartbeat_monitor": {
            "label": "POULS",
            "detail": "Stress détecté",
            "icon": "radio",
            "family": "signal",
        },
        "voice_print": {
            "label": "EMPREINTE VOCALE",
            "detail": "Voix isolée",
            "icon": "radio",
            "family": "signal",
        },
        "signal_jammer": {
            "label": "BROUILLAGE",
            "detail": "Signal perturbé",
            "icon": "radio",
            "family": "signal",
        },
        "satellite_sweep": {
            "label": "SATELLITE",
            "detail": "Balayage orbital",
            "icon": "pin",
            "family": "map",
        },
        "map_pin_drop": {
            "label": "POINT CARTE",
            "detail": "Repère ajouté",
            "icon": "pin",
            "family": "map",
        },
        "proximity_alert": {
            "label": "PROXIMITÉ",
            "detail": "Plus proche qu'on croit",
            "icon": "warning",
            "family": "alert",
        },
        "power_cut": {
            "label": "COUPURE",
            "detail": "Lumière instable",
            "icon": "warning",
            "family": "alert",
        },
        "neon_bar": {
            "label": "BAR ORDINAIRE",
            "detail": "Lieu public réel",
            "icon": "pin",
            "family": "alert",
        },
        "searchlight": {
            "label": "PROJECTEUR",
            "detail": "Zone fouillée",
            "icon": "eye",
            "family": "search",
        },
        "basement_elevator": {
            "label": "NIVEAU INFÉRIEUR",
            "detail": "Descente verrouillée",
            "icon": "lock",
            "family": "depth",
        },
        "sealed_door": {
            "label": "PORTE SCELLÉE",
            "detail": "Accès refusé",
            "icon": "lock",
            "family": "blueprint",
        },
        "archive_stamp": {
            "label": "ARCHIVE SCELLÉE",
            "detail": "Dossier classé",
            "icon": "file",
            "family": "file",
        },
        "object_isolate": {
            "label": "OBJET ISOLÉ",
            "detail": "Pièce à conviction",
            "icon": "file",
            "family": "file",
        },
        "crowd_noise": {
            "label": "FOULE",
            "detail": "Témoins potentiels",
            "icon": "eye",
            "family": "signal",
        },
        "room_tone": {
            "label": "SILENCE",
            "detail": "Ambiance anormale",
            "icon": "radio",
            "family": "signal",
        },
    }
)


SEMANTIC_HERO_TYPES = {
    "map_zoom",
    "cctv_scan",
    "search_grid",
    "redacted_report",
    "classified_stamp",
    "year_marker",
    "question_prompt",
    "file_open",
    "missing_poster",
    "last_seen_marker",
    "floor_plan",
    "exit_scan",
    "blind_spot",
    "corridor_scan",
    "entity_radar",
    "radio_signal",
    "audio_waveform",
    "voice_print",
    "mind_control",
    "experiment_chamber",
    "underground_depth",
    "official_denial",
    "case_board",
    "evidence_thread",
}

SEMANTIC_PREF_DUR = {
    "map_zoom": 5.80,
    "satellite_sweep": 5.70,
    "map_pin_drop": 5.45,
    "cctv_scan": 4.85,
    "security_log": 4.60,
    "motion_detector": 4.55,
    "search_grid": 4.70,
    "searchlight": 4.80,
    "proximity_alert": 4.65,
    "redacted_report": 4.35,
    "classified_stamp": 4.20,
    "archive_stamp": 4.35,
    "document_leak": 4.40,
    "official_denial": 4.45,
    "breaking_news": 4.35,
    "year_marker": 4.45,
    "calendar_flip": 4.55,
    "time_jump": 4.60,
    "question_prompt": 4.65,
    "file_open": 4.45,
    "missing_poster": 4.45,
    "last_seen_marker": 4.35,
    "underground_depth": 4.65,
    "route_trace": 4.45,
    "floor_plan": 4.60,
    "exit_scan": 4.50,
    "blind_spot": 4.50,
    "mind_control": 4.65,
    "experiment_chamber": 4.65,
    "timeline_split": 4.55,
    "power_cut": 4.50,
    "neon_bar": 4.50,
    "room_tone": 4.35,
}


def _overlay_preferred_duration(spec):
    otype = spec.get("type")
    return SEMANTIC_PREF_DUR.get(
        otype, 4.15 if otype not in SEMANTIC_HERO_TYPES else 4.45
    )


SEMANTIC_VARIANT_ROTATION = {
    "classified_stamp": [
        "classified_stamp",
        "archive_stamp",
        "document_leak",
        "redacted_report",
        "official_denial",
        "file_open",
        "case_board",
        "evidence_thread",
    ],
    "redacted_report": [
        "redacted_report",
        "document_leak",
        "archive_stamp",
        "file_open",
        "official_denial",
        "case_board",
    ],
    "file_open": [
        "file_open",
        "archive_stamp",
        "object_isolate",
        "document_leak",
        "evidence_thread",
        "case_board",
    ],
    "cctv_scan": [
        "cctv_scan",
        "security_log",
        "motion_detector",
        "blind_spot",
        "corridor_scan",
    ],
    "security_log": [
        "security_log",
        "motion_detector",
        "cctv_scan",
        "blind_spot",
    ],
    "search_grid": [
        "search_grid",
        "searchlight",
        "proximity_alert",
        "motion_detector",
        "last_seen_marker",
    ],
    "map_zoom": [
        "map_zoom",
        "satellite_sweep",
        "map_pin_drop",
    ],
    "route_trace": [
        "route_trace",
        "satellite_sweep",
        "map_pin_drop",
        "proximity_alert",
    ],
    "year_marker": [
        "year_marker",
        "calendar_flip",
        "time_jump",
        "timeline_split",
    ],
    "timeline_pin": [
        "timeline_pin",
        "calendar_flip",
        "time_jump",
        "case_board",
    ],
    "question_prompt": [
        "question_prompt",
        "theory_stack",
        "case_board",
    ],
    "mind_control": [
        "mind_control",
        "memory_flash",
        "experiment_chamber",
        "timeline_split",
    ],
    "underground_depth": [
        "underground_depth",
        "basement_elevator",
        "sealed_door",
        "thermal_scan",
    ],
}


def _diversify_overlay_types(overlays, scene_idx):
    """Évite l'impression de boucle en variant le type exact et la famille visuelle."""
    diversified = []
    used_types = set()
    used_families = set()
    scene_idx = scene_idx or 0
    for rank, spec in enumerate(overlays):
        original = spec.get("type")
        candidates = list(SEMANTIC_VARIANT_ROTATION.get(original, [original]))
        if original == "map_zoom" and scene_idx <= 1:
            candidates = ["map_zoom", "satellite_sweep", "map_pin_drop"]
        else:
            shift = (scene_idx + rank * 2) % max(1, len(candidates))
            candidates = candidates[shift:] + candidates[:shift]

        chosen = None
        for cand in candidates:
            if cand not in SEMANTIC_META or cand in used_types:
                continue
            family = SEMANTIC_META.get(cand, {}).get("family")
            if family in used_families and len(candidates) > 1:
                continue
            chosen = cand
            break
        if chosen is None:
            for cand in candidates:
                if cand in SEMANTIC_META and cand not in used_types:
                    chosen = cand
                    break
        if chosen is None:
            chosen = original

        new_spec = dict(spec)
        new_spec["type"] = chosen
        diversified.append(new_spec)
        used_types.add(chosen)
        used_families.add(SEMANTIC_META.get(chosen, {}).get("family"))
    return diversified


def _prepare_overlay_schedule(overlays, audio_duration, scene_idx):
    """Décale les overlays pour éviter les recouvrements frame par frame."""
    if not overlays:
        return []
    base = 0.82
    end_guard = 1.10
    gap = 0.95
    available = max(0.0, audio_duration - base - end_guard)
    max_items = 2 if available >= 9.8 else 1
    curated = overlays[:max_items]

    if len(curated) == 1 or available < 4.9:
        spec = curated[0]
        spec["_start_offset"] = min(base, max(0.18, audio_duration * 0.22))
        room = audio_duration - spec["_start_offset"] - end_guard
        if room <= 3.10:
            spec["_duration"] = max(1.50, room)
        else:
            spec["_duration"] = max(3.10, min(_overlay_preferred_duration(spec), room))
        return [spec]

    first, second = curated[0], curated[1]
    first_pref = _overlay_preferred_duration(first)
    second_pref = _overlay_preferred_duration(second)
    first_dur = min(first_pref, max(4.05, available * 0.50))
    second_start = base + first_dur + gap
    second_room = audio_duration - second_start - end_guard
    if second_room < 3.35:
        first["_start_offset"] = base
        first["_duration"] = max(3.60, min(first_pref, available))
        return [first]

    first["_start_offset"] = base
    first["_duration"] = first_dur
    second["_start_offset"] = second_start
    second["_duration"] = max(3.35, min(second_pref, second_room))
    second["_secondary"] = True
    return [first, second]
