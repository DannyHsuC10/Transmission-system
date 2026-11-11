import {writeDxf, writeStep} from "./cad-export.js";

self.onmessage = ({data: {gear, format, outerDiameter, thickness}}) => {
  try {
    self.postMessage({content: format === "STEP" ? writeStep(gear, outerDiameter, thickness) : writeDxf(gear, outerDiameter)});
  } catch (error) {
    self.postMessage({error: error.message});
  }
};
