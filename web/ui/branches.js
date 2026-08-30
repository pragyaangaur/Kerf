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
    id: 'rename-pitch',
    name: 'rename bolt_pitch to hole_pitch',
    story: 'Tidying up the names, so bolt_pitch becomes hole_pitch everywhere it is used.',
    apply: (part) => {
      part.parameters.hole_pitch = part.parameters.bolt_pitch;
      delete part.parameters.bolt_pitch;
      for (const feature of part.features) {
        for (const [key, value] of Object.entries(feature)) {
          if (Array.isArray(value)) {
            feature[key] = value.map((item) => (typeof item === 'string'
              ? item.replace(/bolt_pitch/g, 'hole_pitch') : item));
          } else if (typeof value === 'string' && key !== 'name' && key !== 'id') {
            feature[key] = value.replace(/bolt_pitch/g, 'hole_pitch');
          }
        }
      }
    },
  },
  {
    id: 'fifth-bolt',
    name: 'add a fifth mounting hole',
    story: 'One more hole on the motor face, placed from bolt_pitch like the others.',
    apply: (part) => {
      part.features.push({
        id: 'bolt_e', type: 'cylinder', op: 'subtract', name: 'motor bolt centre',
        radius: 'bolt_d/2', height: 40, axis: 'y',
        center: ['bolt_pitch/2', 'plate_d/2 - wall_t/2', 'rise - 6'],
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
