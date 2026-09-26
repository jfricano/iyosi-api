# iYosi — product brief

## Origin story

While living in Manila during COVID, I found it difficult to distinguish designated smoking areas from places people mentioned by word of mouth. I no longer smoke, but that information gap stayed with me. iYosi is an attempt to make the information visible, current, and honest about what is actually verified, while supporting smoke-free rules and shared air.

— Jason Fricano, for Orca Solutions

## Promise

Open the map, find a nearby place, and understand what the community knows about it before walking over. People can help by adding a place, confirming whether it is still there, rating the experience, leaving a useful review, or reporting an error. The product should make it easier to use designated areas and easier to correct misleading pins.

The first launch covers the National Capital Region (NCR). Android is the first client. The server contract is platform neutral so an iOS client can follow without reworking the data model.

## The map

- Start centered on Metro Manila, cluster pins when zoomed out, and let users toggle each place type.
- Search an address or landmark, jump to the result, then browse places nearby.
- Offer GPS as an optional shortcut. Search and browsing work without location permission.
- Let contributors drag a pin to the reported smoking area and, if different, add a second pin for the **public entrance or usable access point**. A short access note can describe the floor, gate, operating hours, or whether the area is outdoors.
- On every place card, show type, verification label, last confirmation date, rating, review count, and any closure or dispute warning before directions.
- Use distinct shapes as well as colors so types remain readable at a glance.

## Four user-facing place types

| Type | What it means | Initial treatment |
| --- | --- | --- |
| Public designated area | A designated smoking area supported by current signage, operator information, or other reviewable evidence | Show as **verified** only after admin review of evidence |
| Establishment designated area | A venue has a specifically designated area with reviewable evidence | Show as **verified** only after admin review; state whether it is inside or outside |
| Community-reported outdoor spot | People report smoking at an outdoor spot, including places where smoking may be prohibited | Label **unverified** or **prohibited** as evidence warrants; never imply it is legal or safe from enforcement |
| Establishment claim | A venue or user says smoking is allowed, but designated-area status is unclear | Label **unverified** until evidence establishes a designated area |

These are **place descriptions**, not a legal ranking. A separate status records `verified_designated`, `community_reported`, `disputed`, `prohibited`, or `closed`. This keeps the original word-of-mouth category visible without presenting a hidden or prohibited spot as an approved one. Local rules and property rules can change. Ratings and confirmations cannot promote a place to `verified_designated`; only evidence review can.

## Core contribution flow

1. A person at least 18 years old browses the map. Sign-in is required to contribute, not to browse.
2. To add a place, they choose a type, move the pin, give it a name or landmark, describe access, and say how they know the place exists. The app checks for nearby duplicates before submission.
3. A new place enters moderation. In v1, every proposed pin stays pending until an admin publishes it. An informal spot can then appear with an **unverified** or **prohibited** label; a claim of official designation needs evidence review.
4. A confirmation answers a narrow question: **is this place and access route still there?** It records `still_there`, `changed`, or `gone`, optional access-note correction, and an observation time.
5. A rating answers a different question: **how was the experience?** One to five stars plus optional written comments. It never changes permission status.
6. Signed-in contributors can flag a place, review, or access note for inaccurate status, closure, privacy, harassment, spam, or another policy issue. Admins can hide, correct, merge, or remove content and record why.

## Release 1: Android + shared API

**Must have:** NCR map and filters; address search; optional GPS; precise pin placement; four place types and visible verification status; place detail; add and duplicate check; confirmation; separate rating and written review; access notes; report flow; admin queue and actions; basic account and age gate; privacy notice and deletion request path.

**Quality bar:** Clear empty states, slow-network handling, readable map labels, abuse rate limits, no background location collection, and a fresh-or-stale indicator. Accessibility includes text alternatives for pin colors and controls usable with screen readers.

**Success signals:** Monthly active adults in NCR, searches that lead to a viewed place, share of visible places confirmed recently, time to resolve reports, duplicate rate, and correction rate. Track these in aggregate rather than keeping a location trail of individual users.

**Out of scope for v1:** Live tracking of guards, police, or military; hidden/enforcement-avoidance instructions; social feeds; payments; advertising; and a public claim that the map certifies legal status. The security-presence icon idea remains a v2 discussion, not a committed feature.

## How it changes a trip across the metro

Someone leaving a mall or arriving in an unfamiliar neighborhood can search the address, filter for a designated area, check the latest confirmation and access note, and decide whether the walk is worthwhile. A regular can correct a moved or closed area in seconds. A venue can point out a real designated space instead of relying on vague directions. Over time, the map becomes less of a rumor chain and more of a maintained public guide.

## Name directions

| Name | Feel | Note |
| --- | --- | --- |
| **iYosi** | Short, app-like, already the project name | Best working name until a brand check |
| **Kuya Yosi** | Warm, conversational local guide | Strong character, but personifies the app as a male guide |
| **Yosi Kuya** | Playful and distinctly Filipino | Memorable, slightly less natural as a phrase |
| **Saan Yosi?** | Directly asks “where to smoke?” | Clear map promise; punctuation may complicate handles |
| **Yosi Dito** | “Smoke here” | Catchy, but could sound like permission at unverified spots |
| **Tara, Yosi** | Social, invitation-like | Less clear that this is a place finder |

Working recommendation: keep **iYosi** for the repository and prototype; test **Kuya Yosi** and **Saan Yosi?** with Manila users before committing to a store name. Check trademarks, domains, and app stores before launch.
