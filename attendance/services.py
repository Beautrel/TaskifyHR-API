"""Règles du pointage : position dans la zone, une entrée et une sortie par jour."""
from math import asin, cos, radians, sin, sqrt

from django.conf import settings

from .models import WorkSite


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance en mètres entre deux points GPS (formule de haversine)."""
    r = 6_371_000
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))


def default_site() -> WorkSite:
    site = WorkSite.objects.first()
    if site is None:
        site = WorkSite.objects.create(**settings.TASKIFY["DEFAULT_SITE"])
    return site


def is_in_zone(latitude: float, longitude: float) -> bool:
    if not settings.TASKIFY["ENFORCE_ZONE"]:
        return True
    site = default_site()
    return distance_m(latitude, longitude, site.latitude, site.longitude) <= site.radius_m
