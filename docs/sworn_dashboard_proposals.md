# Sworn dashboard — three layout proposals

Design-only, 2026-10-23. Pending owner selection; see
[research](sworn_game_mechanics.md). Reference website and catalog inspected
with headless Playwright. No production dashboard changes.

The layouts below are schematic, not measured 149×45 terminal renders.
Numbers are illustrative, not live readings. The ASCII hives stand in for the
actual square SVG artwork. Filled cells, partial fills, rings and rarity dots
must retain the renderer's colors and geometry in the implementation.

Shared behavior: MaxPane hero frames, dark background and neutral labels;
original artwork colors; full card expansion; safe address copy/explorer links;
cache-first rendering and only visible-view polling; a centered loading footer.
A transferred card's holder and original claimant remain separate identities.

## 1. Card Explorer — recommended

Collection navigation on the left, selected card in the center, facts and evidence on the right. Best balance for regular browsing. The collection hero is global; the other heroes describe the selection.

```text
SWORN / EXPLORER                         [ wallet / token ID ................ ]

+-- o COLLECTION ------+  +-- o FAMILIES --------+  +-- o FACTS -----------+  +-- o COMMUNITY -------+
|                      |  |                      |  |                      |  |                      |
|  +-- MINTED ------+  |  |  +-- SELECTED ----+  |  |  +-- SELECTED ----+  |  |  +-- SELECTED ----+  |
|  |      128       |  |  |  |    10 / 13     |  |  |  |       14       |  |  |  |       4        |  |
|  +----------------+  |  |  +----------------+  |  |  +----------------+  |  |  +----------------+  |
|                      |  |                      |  |                      |  |                      |
+----------------------+  +----------------------+  +----------------------+  +----------------------+

+-- CARDS -----------+  +-- SWORN #42 -------------------------+  +-- FACTS -------------------------+
|ID    FAMILIES      |  |                                      |  |Spawned        held               |
|>42   10/13         |  |          <##>        <**>            |  |Zero-Shot      rare               |
| 41    7/13         |  |                <##>                  |  |Hopper          2/3               |
| 40    9/13         |  |          <..>        <##>            |  |Swarmed        held               |
| 39    6/13         |  |    <##>        <##>        <**>      |  |                                  |
|                    |  |          <##>        <..>            |  |Selected: Swarmed                 |
|/ search            |  |                <##>                  |  |Panel-sworn                       |
|f filter            |  |          <..>        <##>            |  |Accepted proof                    |
|                    |  |                                      |  |Evidence >>                       |
|                    |  |    exact card artwork / square       |  |                                  |
|                    |  |                                      |  |                                  |
|                    |  |                                      |  |                                  |
+--------------------+  +--------------------------------------+  +----------------------------------+

Claimant: <wallet> [copy]    Holder: <wallet> [copy]    Source / metadata >>
q quit   m menu                         loading                         SWORN
```

## 2. Card Gallery

Two large card tiles per page, filters above and selected-card details in a popup. Best for visually comparing cards. Thin rings are smaller here than in the single-card views; fullscreen expansion preserves access to detail.

```text
SWORN / GALLERY                 [ all cards ] [ family: all ] [ newest first ]

+-- o COLLECTION ------+  +-- o FILTER ----------+  +-- o CATALOG ---------+  +-- o CATALOG ---------+
|                      |  |                      |  |                      |  |                      |
|  +-- MINTED ------+  |  |  +-- MATCHES -----+  |  |  +-- FAMILIES ----+  |  |  +-- FACTS -------+  |
|  |      128       |  |  |  |       12       |  |  |  |       13       |  |  |  |       25       |  |
|  +----------------+  |  |  +----------------+  |  |  +----------------+  |  |  +----------------+  |
|                      |  |                      |  |                      |  |                      |
+----------------------+  +----------------------+  +----------------------+  +----------------------+

+-- o SWORN #42 ---------------------------------+  +-- o SWORN #43 ---------------------------------+
|                                                |  |                                                |
|               <##>        <**>                 |  |               <##>        <..>                 |
|                     <##>                       |  |                     <##>                       |
|               <..>        <##>                 |  |               <..>        <##>                 |
|         <##>        <##>        <**>           |  |         <##>        <##>        <..>           |
|               <##>        <..>                 |  |               <##>        <..>                 |
|                     <##>                       |  |                     <##>                       |
|               <..>        <##>                 |  |               <..>        <##>                 |
|                                                |  |                                                |
|  10 / 13 families       2 rare dots            |  |   8 / 13 families       0 rare dots            |
|  claimant <wallet> [copy]                      |  |  claimant <wallet> [copy]                      |
|  selected  >> details / fullscreen             |  |            >> details / fullscreen             |
|                                                |  |                                                |
+------------------------------------------------+  +------------------------------------------------+

< previous                                      showing 1-2 / 12          next >
Selected #42: 14 facts | 4 community facts | original claimant retained
q quit   m menu                         loading                         SWORN
```

## 3. Wallet and Facts

A claimant lookup leads to one dominant card and a fact/evidence inspector. Best for reading an individual wallet. For an unminted wallet, any hypothetical artwork must be explicitly marked as a preview; it is never presented as an issued card.

```text
SWORN / WALLET                     [ claimant address ...................... ]

+-- o CARD ------------+  +-- o FAMILIES --------+  +-- o FACTS -----------+  +-- o COMMUNITY -------+
|                      |  |                      |  |                      |  |                      |
|  +-- TOKEN ID ----+  |  |  +-- HELD --------+  |  |  +-- HELD --------+  |  |  +-- ACCEPTED ----+  |
|  |       42       |  |  |  |    10 / 13     |  |  |  |    14 / 25     |  |  |  |       4        |  |
|  +----------------+  |  |  +----------------+  |  |  +----------------+  |  |  +----------------+  |
|                      |  |                      |  |                      |  |                      |
+----------------------+  +----------------------+  +----------------------+  +----------------------+

+-- o ARTIFACT / SWORN #42 ----------------------------+  +-- WALLET FACTS --------------------------+
|                                                      |  |FAMILY          TIER      EVIDENCE        |
|                   <##>        <**>                   |  |Spawned         held      direct          |
|                         <##>                         |  |Zero-Shot       rare      direct          |
|                   <..>        <##>                   |  |Hopper           2/3      direct          |
|             <##>        <##>        <**>             |  |Swarmed         held      panel           |
|                   <##>        <..>                   |  |                                          |
|                         <##>                         |  |SELECTED FACT: SWARMED                    |
|                   <..>        <##>                   |  |Rule and qualifying job history           |
|                                                      |  |Accepted request / block window           |
|            original artwork / square                 |  |Open proof >>                             |
|                                                      |  |                                          |
|  Claimant: <wallet> [copy]                           |  +------------------------------------------+
|  Holder:   <wallet> [copy]                           |  +-- COMMUNITY -----------------------------+
|  Fullscreen >>                                       |  |4 accepted facts                          |
|                                                      |  |Names / IDs / individual evidence         |
|                                                      |  |Open complete list >>                     |
|                                                      |  |                                          |
+------------------------------------------------------+  +------------------------------------------+

q quit   m menu                         loading                         SWORN
```

## Selection

Recommend 1 as the main dashboard, with the large-art/fullscreen treatment from 3.
A later gallery body can add 2 without forcing tiny previews into the default.
The owner has not yet chosen a layout or answered whether graphics-capable
terminals are acceptable; neither is an implementation approval.
