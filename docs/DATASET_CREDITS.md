# Dataset Credits & Academic Citations (NO-CAP / SIH26188)

This document records formal academic citations, origins, and attribution credits for datasets used in training, benchmarking, and evaluating document detection and forensic models in NO-CAP.

---

## 1. MIDV-2020: A Dataset for Identity Document Analysis and Recognition on Mobile Devices in Video Stream

**Website**: http://l3i-share.univ-lr.fr/MIDV2020/midv2020.html  
**Authors**: Konstantin Bulatov, Daniil Matalov, Vladislav Arlazarov, Vladimir V. Arlazarov, et al.  
**BibTeX Citation**:
```bibtex
@inproceedings{bulatov2020midv,
  title={MIDV-2020: A Dataset for Identity Document Analysis and Recognition on Mobile Devices in Video Stream},
  author={Bulatov, Konstantin and Matalov, Daniil and Arlazarov, Vladislav V. and Arlazarov, Vladimir V.},
  booktitle={Proceedings of the 30th International Conference on Computer Graphics and Vision (GraphiCon 2020)},
  pages={1--10},
  year={2020}
}
```
**Usage in Project**: Document card localization training and held-out cross-condition evaluation across 8 physical capturing environments.

---

## 2. MIDV-500: A Dataset for Identity Documents Modelling and Recognition in Video Stream

**Website**: https://smartengines.com/midv-500/  
**Authors**: Vladimir V. Arlazarov, Konstantin Bulatov, Timofey Chernov, Daniil Matalov, et al.  
**BibTeX Citation**:
```bibtex
@article{arlazarov2019midv,
  title={MIDV-500: A dataset for identity documents modelling and recognition in video stream},
  author={Arlazarov, Vladimir V and Bulatov, Konstantin and Chernov, Timofey and Arlazarov, Vladislav V},
  journal={Computer Optics},
  volume={43},
  number={5},
  pages={818--824},
  year={2019}
}
```
**Usage in Project**: Video frame captures, quad boundary ground truth, and Machine Readable Zone (MRZ) line ground truth.

---

## 3. FantasyID: Printed Identity Document Dataset with Physical and Digital Manipulations

**Repository**: Zenodo (Record 17063366)  
**URL**: https://zenodo.org/records/17063366  
**Usage in Project**: Real-world phone captures of physically printed cards, evaluated for card boundary localization and forgery detection benchmark.

---

## 4. Mendeley Synthetic Indian Aadhaar Dataset

**Repository**: Mendeley Data  
**URL**: https://data.mendeley.com/datasets/wk6n8fhx3c/1  
**DOI**: 10.17632/wk6n8fhx3c.1  
**Usage in Project**: Fictitious synthetic templates for evaluating document classification without real PII.

---

## 5. Roboflow Community Computer Vision Datasets

Attributed according to community publication policies:
- `voterid/voterid-duejn`: Voter ID card field and document bounding boxes.
- `ocr-aadhar/voter_id-qiygw`: Indian Electoral photo identity card boundary annotations.
- `kmit-ehbhz/pan-cards`: Permanent Account Number (PAN) card field boundary annotations.
- `documentpii/driving-license-project-myeri`: Indian Driving Licence field bounding boxes.
- `jaspreetsingh/indian-driving-licence-reader-rlxel`: Indian Driving Licence format annotations.
- `subhransusarangi/aadhaar-front-icx0u-onkhu`: Aadhaar card front face boundary annotations.

---

## 6. Project Synthetic Generators

- `training/synth_fields.py`: Clean-room procedural generator of synthetic specimens carrying prominent "SPECIMEN – NOT A VALID DOCUMENT" watermarks with sample strings ("SAMPLE NAME", "0000 0000 0000") and geometric placeholder emblems.
- `training/indian_specimens/make_specimen_sheets.py`: Print-ready 300 DPI A4 specimen sheets for physical field photography.
