# Governors: rewarded for votes or for loyalty? (written 20 October 2026, before computing)

## Units
Constitutional PRI governors (party PNR/PRM/PRI in the roster) whose tenure began 1934-1994, from
`data/governors/governors_roster.csv` (02_*), linked to Camp. Federal District regents, interim, substitute,
provisional and acting governors are excluded (they are not the president's long-term choice for the state).
Opposition governors (1989 on) are excluded.

## Outcome: the next post (Question 1)
The highest rung held in the six years after the tenure ends (end+1..end+6), from the annual ladder used in the main
design (`rank/position_tiers.csv`, rung = floor of the hybrid rank, spells longer than 12 years dropped):
- **Main:** a top post, rung 8 or above (cabinet secretaries, the Federal District, PEMEX, IMSS, CFE are rung 9).
- Secondary: rung 7 or above (adds the Senate and assistant secretaries); no ranked post at all.

## Votes delivered
The PRI candidate's share of the presidential vote in the state in the presidential election held during the tenure
(the last one if two), minus the state's share in the previous presidential election, minus the national change
between the two elections (`output/maps/opposition_vote_by_state.csv`). This is the state's performance relative to
the country in the governor's election, net of the state's own past. 1976 (no opposition candidate) gives no
variation and is set to missing. Secondary: the level, state share minus national share, in that election.
Official counts: what the governor delivered includes what he could manufacture, which is what the centre observed.

## Loyalty
A direct tie (any type in `networks/network_edges.csv`, dated by the end of the tenure or undated) to the president
in office in the year after the tenure ends, who appoints the next post. Secondary: a tie to the president who was in
office when the tenure began.

## Roots (paracaidista vs arraigado)
Posts located in the governed state in the ten years before the tenure (`clean_positions/*`, state, else work_state;
the governorship itself excluded):
- **Rooted:** a state-level post (state government, state legislature, mayor, state or local party committee).
- **Federal legislator only:** the only posts in the state were federal deputy or senator for the state.
- **Parachuted:** no post located in the state.
Born in the state is reported alongside.

## Estimation
Linear probability of a top post on votes delivered (standardized), the tie to the next appointing president, and
roots, with fixed effects for the presidential term in which the tenure ended and for the rung held in the six years
before the governorship, and age at the end. Standard errors clustered by state; a wild cluster bootstrap by
presidential term as a check (about ten clusters).

## Reading, fixed now
Rewarded for votes: the coefficient on votes delivered is positive and comparable in size to the tie. Rewarded for
loyalty: the tie predicts the top post and votes do not. Both, or neither, are possible readings. The roots
coefficient answers whether parachuted governors are rewarded more (the president's men) or less (failed local
operators). With about 300 governors, effects under about 10 percentage points will not be distinguishable from zero.
