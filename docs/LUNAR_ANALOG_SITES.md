# Earth regions with a known lunar/Mars analog use

Checklist for manual verification. **Written from memory, not looked up** - every row needs a source before it goes into a slide.
Confidence: **H** = I am fairly sure, **M** = I recall it but not the details, **L** = guess, check or drop.

The first 8 rows are the regions flagged `validation = true` in `data/regions.csv` (what backend A considers documented analogs).

## Flagged as validation by the backend

| Region (`region` id) | What it is | Use I remember | Conf. | Check at |
|---|---|---|---|---|
| Meteor Crater (`meteor_crater`) | Fresh impact crater, Arizona | Apollo astronaut geology and crater training | H | NASA history of Apollo field training; USGS Astrogeology |
| Cinder Lake (`cinder_lake`) | Artificial crater field near Flagstaff, Arizona | Built 1967-68 by USGS for Apollo crew training and rover/camera tests | H | USGS Astrogeology "Cinder Lake" |
| Craters of the Moon (`craters_of_the_moon`) | Basalt lava field, Idaho | Apollo 14 crew training (1969); later NASA BASALT field tests (with Hawaii) | M | NPS "Craters of the Moon" astronauts page |
| Pinacate (`pinacate`) | Volcanic field with maar craters, Sonora, Mexico | Apollo-era astronaut geology training (mid 1960s) | M | Apollo field training lists |
| Ries (`ries`) | Impact crater with suevite, Germany | Apollo 14 and Apollo 17 crews trained here (1970, 1972) | M | ESA / Ries museum pages |
| Rio Grande Gorge (`rio_grande_gorge`) | Basalt canyon, New Mexico | Apollo-era geology field training (details unknown) | L | USGS / NASA Johnson field training notes |
| Haughton (`haughton`) | Impact crater, Devon Island, Canada | Haughton-Mars Project (Mars Institute / NASA); lunar rover and EVA field tests | H | Mars Institute "Haughton-Mars Project" |
| Mauna Kea (`mauna_kea`) | Volcano, Hawaii (ash and cinder) | NASA lunar ISRU/RESOLVE field tests, PISCES lunar regolith simulant | M | PISCES; NASA RESOLVE 2008 field test |

## Other regions in the index where I recall a use

| Region | Use I remember | Conf. |
|---|---|---|
| Askja (`askja`) | Apollo 11 and 12 crews (and others) trained in Askja caldera, Iceland (1965, 1967) | H |
| Odadahraun (`odadahraun`) | Highland lava desert around Askja, same training area | M |
| Mauna Loa (`mauna_loa`) | Hawaii volcano; NASA lunar and Mars rover and ISRU field tests | M |
| Dry Valleys (`dry_valleys`) | Antarctica; Mars analog (Viking-era tests, polar ice) | M |
| Atacama (`atacama`) | Chile; Mars analog (NASA life-detection and rover field tests) | H |
| Lanzarote (`lanzarote`) | Spain; ESA PANGAEA astronaut geology training | M |
| Etna (`etna`) | Italy; ESA volcano/rover analog tests | L |
| Sverrefjell (`sverrefjell`) | Svalbard; Mars analog (AMASE expeditions) | M |
| Sittampundi (`sittampundi`) | India; anorthosite studied as a lunar highlands analog | M |
| Jingpo Lake (`jingpo_lake`) | China; basalt field used as a lunar analog | L |
| Lonar (`lonar`) | India; basalt impact crater, Moon/Mars analog | M |
| Dalangtan (`dalangtan`) | China; Mars analog (evaporites) | L |
| Danakil (`danakil`) | Ethiopia; Mars analog | M |
| Death Valley (`death_valley`) | USA; Mars and rover test site | L |
| Black Rock (`black_rock`) | Nevada playa; rover/analog test site | L |

All other regions in `data/regions.csv` are not annotated.

## How to verify quickly

1. Search the region name with "Apollo training", "lunar analog" or "NASA analog".
2. Useful starting points: SSERVI analog site pages, USGS Astrogeology, NASA "Analog Missions" pages, ESA PANGAEA.
3. Fill the "Source" column yourself, remove rows with confidence L that you cannot confirm.
