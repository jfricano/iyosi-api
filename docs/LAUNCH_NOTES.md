# Launch notes and open decisions

## Accuracy and moderation

The map is a crowdsourced guide, not a legal authorization service. Philippine Executive Order No. 26 defines designated smoking areas and restricts smoking in enclosed public places and public conveyances; Metro Manila local ordinances and venue rules can be stricter. A 2019 national clarification discusses outdoor areas such as sidewalks, but that does not override local or property rules. Every “approved” claim therefore needs evidence review and a date. A sign, venue confirmation, or official listing can support the label; an anecdote or several positive votes cannot.

Publication rules: hold designated-area claims for admin review; label informal outdoor and venue claims `community_reported` unless evidence supports `prohibited`; quickly hide precise private-property or sensitive-location pins; route “closed,” “prohibited,” and “wrong approval” reports to the top of the queue. A known prohibited spot may remain visible as a warning, but it should not receive a “go here” treatment. Access notes should explain how to reach a public area, not how to evade staff or enforcement. Do not collect or map live security, police, or military locations in v1.

Review rules: prohibit personal attacks, identifying information about workers, trespass directions, deceptive legal claims, and spam. Give contributors a correction path, venue operators a claim/correction path, and admins an audit log. Make the reporting flow available from both place details and individual reviews.

## Privacy and age

The Philippine Data Privacy Act calls for transparent, legitimate, proportionate collection and limited retention. Browse without sign-in; ask for foreground GPS only when the user taps “near me”; do not collect background tracks. Store a selected place pin and account contribution history, not movement history. Publish a privacy notice, retention schedule, deletion route, and contact before launch. Use adult-only access and review the practical age-assurance method before a public release.

## Marketing and eventual revenue

The early message is practical: **“Alam mo ba kung saan? Now everyone does.”** Show a clear map, freshness dates, and honest status labels. Seed the map with verified designated areas first; invite corrections from local residents and venue operators; measure whether people find useful locations and whether reports get resolved quickly. Avoid portraying the app as a way around smoke-free rules.

Advertising is a possible later model, but the v1 experience has no ads. If ads are introduced, keep them away from map controls and place-status labels, disclose sponsorship, and never let payment buy a verification badge or ranking. Tobacco and vape promotion is heavily regulated in the Philippines, including limits on internet and mass-media advertising, so any smoking-adjacent category needs local legal review before sale. Safer possibilities to assess later include neutral local-service sponsorships or a business verification workflow that charges for administrative service while preserving independent status decisions.

## Hosting later

The same containerized API can move to a managed host or a self-hosted PC. A family-built PC could support a small pilot if it has reliable internet, power, backups, security updates, and remote recovery. Do not publish a public service from it before those operational checks. Keep database backups outside the machine. Neither production hosting nor public launch is part of this preparation step.

## Decisions still needed before Android or public launch

1. Final store/brand name after user testing and trademark search.
2. Public age-assurance and account-recovery method; private pilot uses self-attested email/password accounts.
3. Map tile and address-search providers, including cost and terms.
4. Review of boundary-edge disputes; private pilot uses the committed geoBoundaries NCR polygon.
5. Moderation staffing and evidence handling; v1 accepts signage, venue confirmation, or official listing with admin review.
6. Legal and privacy review before public launch, especially local ordinances and any future advertising.

## Primary sources checked 2026-09-25

- [Executive Order No. 26 (2017), Supreme Court E-Library](https://elibrary.judiciary.gov.ph/thebookshelf/showdocs/5/76731)
- [2019 clarification on Executive Order No. 26, Office of the President PDF](https://customs.gov.ph/wp-content/uploads/2023/01/cmc-03-2019_Clarification_on_the_Implementation_of_EO_No_26.pdf)
- [MMDA Resolution No. 11-19, Supreme Court E-Library](https://elibrary.judiciary.gov.ph/thebookshelf/showdocs/11/52295)
- [Republic Act No. 9211, Supreme Court E-Library](https://elibrary.judiciary.gov.ph/thebookshelf/showdocs/2/314)
- [Republic Act No. 11900, Supreme Court E-Library](https://elibrary.judiciary.gov.ph/thebookshelf/showdocs/2/95621)
- [Republic Act No. 10173, National Privacy Commission](https://privacy.gov.ph/data-privacy-act/)

## API implementation note (2026-09-25)

The private pilot API uses self-attested adult registration and has a deletion-request queue. These are implementation defaults, not a public-launch age-assurance or privacy approval. The operator must publish a privacy notice/contact, decide a retention schedule for account, evidence, report, audit, idempotency, and rate-limit data, and review how deletion requests affect legally required records. The admin bootstrap is an operator-only command; production admin provisioning and recovery need a controlled process. The committed NCR seed attributes geoBoundaries (CC BY 3.0 IGO; source NAMRIA/PSA/OCHA); its simplified edges should be checked for disputed boundary locations. Map tiles and geocoding require provider terms, pricing, and usage review before Android integration. Do not put the API on a public host until the operational and legal checks above are complete.
