;;; Project Lucca — Functional Scheme Spatial DSL
;;; Spec 05 / WO-29 Module 1
;;; High-level declarative spatial forms, macros, and geometric constructors

;; Square constructor: (square x y size) -> (rect x y size size)
(defmacro square (x y size)
  (rect x y size size))

;; Origin 2D point constructor
(defmacro origin-2d ()
  (point 0 0))

;; Origin 3D point constructor
(defmacro origin-3d ()
  (point 0 0 0))

;; Unit circle at origin
(defmacro unit-circle ()
  (circle 0 0 1))

;; Unit square at origin
(defmacro unit-square ()
  (rect 0 0 1 1))
