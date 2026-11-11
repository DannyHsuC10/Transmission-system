import {findGearCombinations} from "./gear-model.js";

self.onmessage = ({data: {design, criteria}}) => {
  try {
    self.postMessage({result: findGearCombinations(design, criteria)});
  } catch (error) {
    self.postMessage({error: error.message});
  }
};
