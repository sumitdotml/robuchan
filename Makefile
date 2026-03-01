# install required python and node packages.
setup:
	uv sync
	cd demo-video; npm install
	cd ..

# make live edits
preview:
	cd demo-video && npm start

# outputs a video file
render:
	cd demo-video && npm run build
