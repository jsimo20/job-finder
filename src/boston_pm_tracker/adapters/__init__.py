from .ashby import fetch as fetch_ashby
from .greenhouse import fetch as fetch_greenhouse
from .lever import fetch as fetch_lever

REGISTRY = {
    "ashby": fetch_ashby,
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
}
