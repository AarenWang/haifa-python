(define make-counter
  (lambda ()
    (let ((value 0))
      (lambda ()
        (set! value (+ value 1))
        value))))

(define counter (make-counter))
(list (counter) (counter) (counter))
