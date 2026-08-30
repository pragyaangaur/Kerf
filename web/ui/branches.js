// The edits the merge tab offers, written as changes to the bracket.
//
// These stand in for two people working at the same time. Each one names what
// the person was trying to do, because that is what a merge has to preserve.

export const BRANCHES = [
  {
    id: 'none',
    name: 'no change',
    story: 'This side stayed where the ancestor was.',
    apply: () => {},
  },
  {
    id: 'bore-fit',
    name: 'open the motor bore',
    story: 'The motor boss was a press fit, so the bore opens from 22 to 23.5.',
    apply: (part) => {
      part.parameters.bore_d = 23.5;
    },
  },
  {
    id: 'thicker-plate',
    name: 'thicken the base plate',
    story: 'Prints flexed under belt tension, so the base plate goes from 5 to 8.',
    apply: (part) => {
      part.parameters.plate_t = 8;
    },
  },
  {
    id: 'mount-slots',
    name: 'slot the chassis mounts',
    story: 'The chassis screws become slots so belt tension can be set by hand.',
    apply: (part) => {
      part.parameters.slot_len = 9;
      part.features.push({
        id: 'slot_l', type: 'box', op: 'subtract', name: 'chassis slot L',
        size: ['slot_len', 6, 30], center: [-22, -14, 0],
      });
      part.features.push({
        id: 'slot_r', type: 'box', op: 'subtract', name: 'chassis slot R',
        size: ['slot_len', 6, 30], center: [22, -14, 0],
      });
    },
  },
  {
    id: 'cable-tie',
    name: 'add a cable tie slot',
    story: 'A slot on the right hand side to route the motor cable.',
    apply: (part) => {
      part.features.push({
        id: 'tie_slot', type: 'box', op: 'subtract', name: 'cable tie slot',
        size: [4, 30, 12], center: [22, -14, 6],
      });
    },
  },
  {
    id: 'corner-gusset',
    name: 'add a corner gusset',
    story: 'A gusset behind the riser to stop the bracket flexing.',
    apply: (part) => {
      part.features.push({
        id: 'gusset', type: 'box', op: 'add', name: 'corner gusset',
        size: [8, 26, 26], center: [0, 4, 13], round: 1, blend: 4,
      });
    },
  },
  {
    id: 'raise-face',
    name: 'raise the motor face',
    story: 'The pulley fouled the frame, so the whole riser goes up by 6 mm.',
    apply: (part) => {
      part.parameters.rise = 46;
    },
  },
];

export function branchById(id) {
  return BRANCHES.find((branch) => branch.id === id) || BRANCHES[0];
}
