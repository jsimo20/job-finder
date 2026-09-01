from .ashby import fetch as fetch_ashby
from .ashby import fetch_detail as fetch_ashby_detail
from .greenhouse import fetch as fetch_greenhouse
from .lever import fetch as fetch_lever
from .workday import fetch as fetch_workday
from .workday import fetch_detail as fetch_workday_detail

REGISTRY = {
    "ashby": fetch_ashby,
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "workday": fetch_workday,
}

# Providers whose list payload has no JD; collect calls these for kept
# postings only, so a 1000-role board costs pages + a handful of details.
DETAIL_REGISTRY = {
    "ashby": fetch_ashby_detail,
    "workday": fetch_workday_detail,
}
