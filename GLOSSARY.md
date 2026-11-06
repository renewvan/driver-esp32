# Glossary

**Variant**:
A kind of firmware, for example `esp32-16x-relay`. A variant is built once and can run on any number of boards. It is never visible on the bus.

**Board**:
One physical unit running a variant, identified by a name its owner chooses once when flashing it. A van can have any number of boards, including several of the same variant.

**Driver**:
What a board appears as on the bus: one Driver per board, with its own key, info, health and entities. Not to be confused with a variant, which is only the firmware.
